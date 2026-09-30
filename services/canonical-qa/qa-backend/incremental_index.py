"""Persistent incremental vector/BM25 index for uploaded documents.

The packaged GitHub index is immutable. This module keeps uploaded material in
a separate small index that can be atomically replaced per document and
survives container restarts through the mounted data directory.
"""
from __future__ import annotations

import asyncio
import os
import pickle
import tempfile
import threading
from pathlib import Path
from typing import Any

import jieba
import numpy as np
from rank_bm25 import BM25Okapi


INDEX_VERSION = 1


def _tokens(text: str) -> list[str]:
    return [token for token in jieba.cut_for_search(text) if token.strip()]


class IncrementalIndex:
    def __init__(self, path: Path, embedding_func):
        self.path = path
        self.embedding_func = embedding_func
        self.embeddings = np.empty((0, 1024), dtype=np.float32)
        self.meta: list[dict[str, Any]] = []
        self.corpus_tokens: list[list[str]] = []
        self.bm25: BM25Okapi | None = None
        self._lock = asyncio.Lock()
        self._state_lock = threading.RLock()
        self.loaded = False

    @property
    def record_count(self) -> int:
        return len(self.meta)

    @property
    def document_count(self) -> int:
        return len({item.get("document_id") for item in self.meta})

    def load(self) -> None:
        if self.loaded:
            return
        self.loaded = True
        if not self.path.exists():
            return
        try:
            with self.path.open("rb") as stream:
                data = pickle.load(stream)
            embeddings = np.asarray(data.get("embeddings", []), dtype=np.float32)
            meta = data.get("meta", [])
            corpus = data.get("corpus_tokens", [])
            if embeddings.ndim != 2 or embeddings.shape[1] != 1024 or len(embeddings) != len(meta):
                raise ValueError("invalid incremental embedding shape")
            if len(corpus) != len(meta):
                corpus = [_tokens(str(item.get("b", ""))) for item in meta]
            self.embeddings = embeddings
            self.meta = list(meta)
            self.corpus_tokens = list(corpus)
            self.bm25 = BM25Okapi(self.corpus_tokens) if self.corpus_tokens else None
            print(
                f"[startup] Incremental index loaded: {self.document_count} documents, "
                f"{self.record_count} chunks",
                flush=True,
            )
        except Exception as exc:
            # Do not hide a corrupt incremental file: the base index remains
            # usable, while the health endpoint exposes the reset state.
            print(f"[startup] WARNING: incremental index ignored: {exc}", flush=True)
            self.embeddings = np.empty((0, 1024), dtype=np.float32)
            self.meta = []
            self.corpus_tokens = []
            self.bm25 = None

    def _persist(
        self,
        embeddings: np.ndarray,
        meta: list[dict[str, Any]],
        corpus_tokens: list[list[str]],
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": INDEX_VERSION,
            "dim": 1024,
            "embeddings": embeddings,
            "meta": meta,
            "corpus_tokens": corpus_tokens,
        }
        fd, temp_name = tempfile.mkstemp(prefix="incremental-", suffix=".pkl", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
            # fsync 父目录，确保 rename 在断电后也不丢失
            dir_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            Path(temp_name).unlink(missing_ok=True)

    async def upsert(
        self,
        *,
        document_id: str,
        filename: str,
        title: str,
        primary_category: str,
        secondary_categories: list[str],
        confidentiality: str | None,
        source_type: str | None,
        checksum_sha256: str | None,
        created_at: str | None,
        chunks: list[dict[str, Any]],
    ) -> dict[str, int | str]:
        if not chunks:
            raise ValueError("at least one chunk is required")
        texts = []
        for chunk in chunks:
            text = str(chunk.get("text", "")).strip()
            if not text:
                raise ValueError("chunk text is empty")
            texts.append(text)

        async with self._lock:
            raw_embeddings = await self.embedding_func(texts)
            vectors = np.asarray(raw_embeddings, dtype=np.float32)
            if vectors.ndim != 2 or vectors.shape != (len(texts), 1024):
                raise ValueError(f"embedding dimension mismatch: {vectors.shape}")
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / np.maximum(norms, 1e-8)

            kept = [
                (vector, meta, tokens)
                for vector, meta, tokens in zip(self.embeddings, self.meta, self.corpus_tokens)
                if str(meta.get("document_id")) != document_id
            ]
            new_meta: list[dict[str, Any]] = []
            for index, (chunk, text) in enumerate(zip(chunks, texts)):
                # chunk 级覆盖（管线快照一条记录一个 chunk 时，引用卡直接
                # 显示该记录的标题/日期/来源/链接，而非合成文档标题）；
                # 上传资料不传这些键，行为与原契约完全一致。
                meta = dict(chunk.get("metadata") or {})
                new_meta.append(
                    {
                        "kind": "upload",
                        "key": f"upload:{document_id}:{index}",
                        "document_id": document_id,
                        "chunk_id": str(chunk.get("chunk_id") or index),
                        "chunk_index": index,
                        "chunk_metadata": meta,
                        "t": str(chunk.get("title") or title or filename),
                        "d": str(chunk.get("record_date") or created_at or ""),
                        "a": str(chunk.get("source_name") or source_type or "上传资料"),
                        "s": str(chunk.get("source_name") or source_type or "上传资料"),
                        "b": text,
                        "fb": text,
                        "as": str(chunk.get("summary") or ""),
                        "c": str(chunk.get("primary_category") or primary_category),
                        "tg": chunk.get("tags") or secondary_categories,
                        "u": str(chunk.get("url") or ""),
                        "filename": filename,
                        "confidentiality": confidentiality,
                        "checksum_sha256": checksum_sha256,
                    }
                )
            kept.extend(
                (vector, meta, tokens)
                for vector, meta, tokens in zip(vectors, new_meta, [_tokens(text) for text in texts])
            )
            with self._state_lock:
                if kept:
                    next_embeddings = np.asarray([item[0] for item in kept], dtype=np.float32)
                    next_meta = [item[1] for item in kept]
                    next_corpus = [item[2] for item in kept]
                    next_bm25 = BM25Okapi(next_corpus)
                else:
                    next_embeddings = np.empty((0, 1024), dtype=np.float32)
                    next_meta = []
                    next_corpus = []
                    next_bm25 = None
                self._persist(next_embeddings, next_meta, next_corpus)
                self.embeddings = next_embeddings
                self.meta = next_meta
                self.corpus_tokens = next_corpus
                self.bm25 = next_bm25

        return {"document_id": document_id, "chunk_count": len(texts), "total_chunks": self.record_count}

    async def remove_document(self, document_id: str) -> int:
        """Remove every chunk belonging to one uploaded document; return the count removed."""
        async with self._lock:
            with self._state_lock:
                if not self.record_count:
                    return 0
                kept = [
                    (vector, meta, tokens)
                    for vector, meta, tokens in zip(self.embeddings, self.meta, self.corpus_tokens)
                    if str(meta.get("document_id")) != document_id
                ]
                removed = self.record_count - len(kept)
                if not removed:
                    return 0
                if kept:
                    next_embeddings = np.asarray([item[0] for item in kept], dtype=np.float32)
                    next_meta = [item[1] for item in kept]
                    next_corpus = [item[2] for item in kept]
                    next_bm25 = BM25Okapi(next_corpus)
                else:
                    next_embeddings = np.empty((0, 1024), dtype=np.float32)
                    next_meta = []
                    next_corpus = []
                    next_bm25 = None
                self._persist(next_embeddings, next_meta, next_corpus)
                self.embeddings = next_embeddings
                self.meta = next_meta
                self.corpus_tokens = next_corpus
                self.bm25 = next_bm25
        return removed

    async def remove_chunks_by_record_keys(self, record_key_shas: list[str]) -> int:
        """按 record_key_sha 删除增量 chunk（record 级 UPDATE/DELETE 用，
        2026-09-30）。同 document 的其他 chunk 不受影响；返回删除数。"""
        keys = {str(k) for k in record_key_shas if k}
        if not keys or not self.record_count:
            return 0
        async with self._lock:
            with self._state_lock:
                kept = []
                removed = 0
                for vector, meta, tokens in zip(
                        self.embeddings, self.meta, self.corpus_tokens):
                    md = meta.get("chunk_metadata") or {}
                    ksha = str(md.get("record_key_sha") or "")
                    if ksha and ksha in keys:
                        removed += 1
                        continue
                    kept.append((vector, meta, tokens))
                if not removed:
                    return 0
                if kept:
                    next_embeddings = np.asarray([item[0] for item in kept], dtype=np.float32)
                    next_meta = [item[1] for item in kept]
                    next_corpus = [item[2] for item in kept]
                    next_bm25 = BM25Okapi(next_corpus)
                else:
                    next_embeddings = np.empty((0, 1024), dtype=np.float32)
                    next_meta = []
                    next_corpus = []
                    next_bm25 = None
                self._persist(next_embeddings, next_meta, next_corpus)
                self.embeddings = next_embeddings
                self.meta = next_meta
                self.corpus_tokens = next_corpus
                self.bm25 = next_bm25
        return removed

    def vector_search(self, query_vector: np.ndarray, top_k: int) -> list[dict[str, Any]]:
        with self._state_lock:
            if not self.record_count:
                return []
            scores = self.embeddings @ query_vector
            top_indices = np.argsort(scores)[::-1][:top_k]
            return [
                {"meta": self.meta[int(index)], "score": float(scores[int(index)])}
                for index in top_indices
            ]

    def bm25_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        with self._state_lock:
            if self.bm25 is None:
                return []
            tokens = _tokens(query)
            if not tokens:
                return []
            scores = self.bm25.get_scores(tokens)
            top_indices = np.argsort(scores)[::-1][:top_k]
            results = []
            query_tokens = set(tokens)
            for index in top_indices:
                position = int(index)
                overlap = len(query_tokens.intersection(self.corpus_tokens[position]))
                if overlap:
                    results.append(
                        {
                            "meta": self.meta[position],
                            "score": max(float(scores[position]), 0.0) + float(overlap),
                        }
                    )
            return sorted(results, key=lambda item: item["score"], reverse=True)


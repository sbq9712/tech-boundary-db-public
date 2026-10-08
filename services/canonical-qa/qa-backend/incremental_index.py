"""Persistent incremental vector/BM25 index for uploaded documents.

The packaged GitHub index is immutable. This module keeps uploaded material in
a separate small index that can be atomically replaced per document and
survives container restarts through the mounted data directory.
"""
from __future__ import annotations

import asyncio
import json
import os
import pickle
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import jieba
import numpy as np
from rank_bm25 import BM25Okapi


INDEX_VERSION = 1

# 墓碑源（server 启动时注入 _RecordOpsStore 实例；独立导入本模块——
# 如离线契约测试/独立工具——时保持 None：写入侧无墓碑可查即不拒绝，
# 语义与「无墓碑状态」一致，不再 NameError）
record_ops_store_provider = None


def _tokens(text: str) -> list[str]:
    return [token for token in jieba.cut_for_search(text) if token.strip()]


class IncrementalIndex:
    EPOCH_FILE = "reset-epoch.json"

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
        # G1/T3（2026-10-02）：损坏检测与恢复信号——
        # corrupt=True 表示「文件存在但加载失败已清空」（此前 health 恒报
        # ready，增量召回静默丢失）；reset_epoch 持久在数据卷（重启不丢），
        # api 侧据此触发已完成任务的幂等重放。
        self.corrupt = False
        self.reset_epoch = self._read_epoch()

    @property
    def record_count(self) -> int:
        return len(self.meta)

    @property
    def document_count(self) -> int:
        return len({item.get("document_id") for item in self.meta})

    def _epoch_path(self) -> Path:
        return self.path.with_name(self.EPOCH_FILE)

    def _read_epoch(self) -> int:
        try:
            data = json.loads(self._epoch_path().read_text("utf-8"))
            return int(data.get("epoch") or 0)
        except Exception:
            return 0

    def _bump_epoch(self) -> int:
        epoch = self._read_epoch() + 1
        try:
            self._epoch_path().parent.mkdir(parents=True, exist_ok=True)
            self._epoch_path().write_text(
                json.dumps({"epoch": epoch,
                            "reset_at": datetime.now(timezone.utc).isoformat()}),
                "utf-8")
        except Exception:
            pass  # epoch 写失败不阻断清空重建——api 侧另有计数兜底
        return epoch

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
            # G1/T3：损坏不再静默——置 corrupt（health 如实报 unhealthy，
            # compose healthcheck 会标记容器），并持久 bump reset epoch
            # 供 api 侧幂等重放已完成任务（重启不丢信号）。
            print(f"[startup] WARNING: incremental index corrupt, reset: {exc}",
                  flush=True)
            self.embeddings = np.empty((0, 1024), dtype=np.float32)
            self.meta = []
            self.corpus_tokens = []
            self.bm25 = None
            self.corrupt = True
            self.reset_epoch = self._bump_epoch()

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

        # 三：版本术语区分——
        #   队列任务修订号 rev（IndexTask.rev，覆盖式重入队递增）与认领代次
        #   （claim_token/租约，二.2）是「任务」层的概念；
        #   chunk.metadata.source_rev 是「记录语义版本」（同一记录身份
        #   record_key_sha 的新旧正文世代）。迟到旧版本拒绝只看后者：
        #   版本高水位按 record_key_sha 聚合、不分 document_id——同文档
        #   （上传记录 UUID 跨世代不变）rev2 晚于 rev10 落地同样必须拒收。
        #   版本判定与状态提交在 self._lock 内一次完成（三.2）：并发
        #   upsert（rev10/rev2 同时到达）时先取锁者提交高水位，后者
        #   在锁内看到最新水位再判定，不再有「检查在锁外」的竞态窗口。
        #   删除拒绝依据（三.3）：墓碑身份直接拒收（检索侧 _result_allowed
        #   本就屏蔽墓碑，这里把拒绝提前到写入侧，省嵌入且回执如实）；
        #   墓碑由 record-mutate update/unblock 解除后，合法高版本可正常
        #   落地（补录=unblock+新版本 upsert 的顺序契约）。
        async with self._lock:
            existing_pairs: set[tuple[str, str]] = set()
            ksha_max_rev: dict[str, int] = {}
            _ops = record_ops_store_provider() if callable(record_ops_store_provider) else record_ops_store_provider
            tombstoned: set[str] = set(_ops.tombstones) if _ops is not None else set()
            for m in self.meta:
                md = m.get("chunk_metadata") or {}
                existing_pairs.add((str(md.get("record_key_sha") or ""),
                                    str(md.get("content_sha") or "")))
                k = str(md.get("record_key_sha") or "")
                rv = md.get("source_rev")
                if k and isinstance(rv, int):
                    if rv > ksha_max_rev.get(k, -1):
                        ksha_max_rev[k] = rv
            deduped = []
            rejected_stale = 0
            rejected_tombstoned = 0
            for chunk, text in zip(chunks, texts):
                md = chunk.get("metadata") or {}
                pair = (str(md.get("record_key_sha") or ""),
                        str(md.get("content_sha") or ""))
                if pair[0] and pair[1] and pair in existing_pairs:
                    continue
                if pair[0] and pair[0] in tombstoned:
                    rejected_tombstoned += 1
                    continue
                rv = md.get("source_rev")
                if (pair[0] and isinstance(rv, int) and pair[0] in ksha_max_rev
                        and rv < ksha_max_rev[pair[0]]):
                    rejected_stale += 1
                    continue
                deduped.append((chunk, text))
            skipped_dup = len(chunks) - len(deduped) - rejected_tombstoned
            if skipped_dup or rejected_stale or rejected_tombstoned:
                print(f"[index] upsert {document_id}: skipped {skipped_dup} duplicate, "
                      f"rejected {rejected_stale} stale-rev, "
                      f"{rejected_tombstoned} tombstoned chunks", flush=True)
            if not deduped:
                # 全拒收/全去重回执：chunk_count（canonical-qa 历史契约键）
                # 与 chunks: 0（upload_ingestion/CI 断言键）同值透出
                return {"document_id": document_id, "chunk_count": 0,
                        "chunks": 0,
                        "skipped_duplicate_chunks": skipped_dup,
                        "rejected_stale_rev_chunks": rejected_stale,
                        "rejected_tombstoned_chunks": rejected_tombstoned,
                        "status": "ready"}
            chunks, texts = [c for c, _ in deduped], [t for _, t in deduped]
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

        return {"document_id": document_id, "chunk_count": len(texts),
                "total_chunks": self.record_count,
                "skipped_duplicate_chunks": skipped_dup,
                "rejected_stale_rev_chunks": rejected_stale}

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

    async def remove_chunks_by_record_keys(
            self, record_key_shas: list[str],
            exclude_content_shas: set[str] | None = None) -> int:
        """按 record_key_sha 删除增量 chunk（record 级 UPDATE/DELETE 用，
        2026-09-30）。同 document 的其他 chunk 不受影响；返回删除数。

        一.2（2026-09-30 幂等更新协议）：exclude_content_shas 非空时保留
        内容哈希命中的新版本 chunk——update 重发不再误删已落地的新版本，
        客户端重试/超时重发/断点恢复全部安全。"""
        keys = {str(k) for k in record_key_shas if k}
        if not keys or not self.record_count:
            return 0
        keep_cshas = {str(c) for c in (exclude_content_shas or set()) if c}
        async with self._lock:
            with self._state_lock:
                kept = []
                removed = 0
                for vector, meta, tokens in zip(
                        self.embeddings, self.meta, self.corpus_tokens):
                    md = meta.get("chunk_metadata") or {}
                    ksha = str(md.get("record_key_sha") or "")
                    csha = str(md.get("content_sha") or "")
                    if ksha and ksha in keys and not (csha and csha in keep_cshas):
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

    def count_chunks_with_content(self, record_key_sha: str, content_sha: str) -> int:
        """指定记录身份下、内容哈希匹配的存活 chunk 数（一.2 幂等回执：
        服务端据此回答「新版本是否已在索引」，客户端据此推进基线）。"""
        ksha = str(record_key_sha or "")
        csha = str(content_sha or "")
        if not ksha or not csha:
            return 0
        n = 0
        for meta in self.meta:
            md = meta.get("chunk_metadata") or {}
            if str(md.get("record_key_sha") or "") == ksha \
                    and str(md.get("content_sha") or "") == csha:
                n += 1
        return n

    async def patch_document_metadata(
        self, document_id: str, patch: dict[str, Any]
    ) -> int:
        """任务二 2.1：按 document_id 原位更新 chunk_metadata（归属回填）。

        - 与 upsert/remove 同一把 async _lock（Codex P1：并发写不竞争持久化）；
        - 只改 meta，不重嵌入、不重分词（embeddings/corpus_tokens 不动，
          内容指纹不受 metadata 影响）；
        - 返回更新的 chunk 数（0 = 文档不在增量索引，幂等无副作用）。
        """
        if not patch:
            return 0
        async with self._lock:
            with self._state_lock:
                patched = 0
                for meta in self.meta:
                    if str(meta.get("document_id") or "") != document_id:
                        continue
                    md = meta.get("chunk_metadata")
                    if not isinstance(md, dict):
                        md = {}
                        meta["chunk_metadata"] = md
                    for key, value in patch.items():
                        md[key] = value
                    patched += 1
                if patched:
                    self._persist(self.embeddings, self.meta, self.corpus_tokens)
                return patched

    def documents_metadata(self) -> dict[str, dict[str, Any]]:
        """按 document_id 聚合存活 chunk 的元数据摘要（状态确认/回填清单用）。

        返回 {document_id: {chunks, content_shas, record_key_shas,
        primary_section, source, checksum_sha256}}——chunks>0 即该文档在
        增量索引中实际可检索（向量/BM25 由同一写入路径保证）。

        Codex P1-4：真实健康检查——chunks 只证明元数据在册；
        vector_rows_ok/bm25_rows_ok 逐 chunk 校验对齐数组中该行
        （embeddings 非零向量 / corpus_tokens 非空词袋），索引结构
        损坏（数组错位/缺行/BM25 未建）时不再误报健康。
        """
        out: dict[str, dict[str, Any]] = {}
        with self._state_lock:
            aligned = (
                len(self.embeddings) == len(self.meta)
                and len(self.corpus_tokens) == len(self.meta)
                and self.embeddings.ndim == 2
            )
            bm25_alive = self.bm25 is not None or not any(
                tokens for tokens in self.corpus_tokens)
            for pos, meta in enumerate(self.meta):
                did = str(meta.get("document_id") or "")
                if not did:
                    continue
                md = meta.get("chunk_metadata") or {}
                entry = out.setdefault(did, {
                    "chunks": 0,
                    "content_shas": set(),
                    "record_key_shas": set(),
                    "primary_section": None,
                    "primary_sections": set(),
                    "content_sha_rows": 0,
                    "intelligence_types": set(),
                    "intelligence_type_rows": 0,
                    "source_versions": set(),
                    "source_version_rows": 0,
                    "source": None,
                    "checksum_sha256": None,
                    "vector_rows_ok": 0,
                    "bm25_rows_ok": 0,
                })
                entry["chunks"] += 1
                if aligned and bool(self.embeddings[pos].any()):
                    entry["vector_rows_ok"] += 1
                if aligned and bm25_alive and bool(self.corpus_tokens[pos]):
                    entry["bm25_rows_ok"] += 1
                csha = str(md.get("content_sha") or "")
                if csha:
                    entry["content_shas"].add(csha)
                    entry["content_sha_rows"] += 1
                for field, plural, count in (("intelligence_type", "intelligence_types", "intelligence_type_rows"),
                                               ("source_version", "source_versions", "source_version_rows")):
                    if md.get(field) is not None:
                        entry[plural].add(str(md[field]))
                        entry[count] += 1
                ksha = str(md.get("record_key_sha") or "")
                if ksha:
                    entry["record_key_shas"].add(ksha)
                entry["primary_section"] = entry["primary_section"] or (
                    md.get("primary_section") or None)
                entry["primary_sections"].add(str(md.get("primary_section") or ""))
                entry["source"] = entry["source"] or (md.get("source") or None)
                entry["checksum_sha256"] = entry["checksum_sha256"] or (
                    meta.get("checksum_sha256") or None)
        for entry in out.values():
            entry["intelligence_types"] = sorted(entry["intelligence_types"])
            entry["source_versions"] = sorted(entry["source_versions"])
            entry["content_shas"] = sorted(entry["content_shas"])
            entry["record_key_shas"] = sorted(entry["record_key_shas"])
            entry["primary_sections"] = sorted(entry["primary_sections"])
        return out

    def vector_search(
        self, query_vector: np.ndarray, top_k: int,
        allowed: Callable[[dict], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """任务二 2.2：allowed 谓词在【候选形成阶段】生效——按来源范围
        （及墓碑/版本门控）先过滤再计满 top_k，小体量源不再被其他源的
        高分 chunk 在全局 top-k*3 截断处挤出（历史缺陷：6 条高分 breadth
        chunk + 1 条可命中 atsc chunk，atsc 范围查询双路 0 召回）。"""
        with self._state_lock:
            if not self.record_count:
                return []
            scores = self.embeddings @ query_vector
            top_indices = np.argsort(scores)[::-1]
            if allowed is None:
                top_indices = top_indices[:top_k]
                return [
                    {"meta": self.meta[int(index)], "score": float(scores[int(index)])}
                    for index in top_indices
                ]
            out: list[dict[str, Any]] = []
            for index in top_indices:
                if len(out) >= top_k:
                    break
                meta = self.meta[int(index)]
                if not allowed(meta):
                    continue
                out.append({"meta": meta, "score": float(scores[int(index)])})
            return out

    def bm25_search(
        self, query: str, top_k: int,
        allowed: Callable[[dict], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """任务二 2.2：同 vector_search——allowed 在候选形成阶段生效。"""
        with self._state_lock:
            if self.bm25 is None:
                return []
            tokens = _tokens(query)
            if not tokens:
                return []
            scores = self.bm25.get_scores(tokens)
            top_indices = np.argsort(scores)[::-1]
            # 计满 top_k：allowed 在计满 top_k 前裁剪不允许的候选——
            # 小体量源在范围内取满；非 allowed 模式维持旧全局截断 + overlap 门。
            kept: list[int] = []
            for index in top_indices:
                if len(kept) >= top_k:
                    break
                if allowed is not None and not allowed(self.meta[int(index)]):
                    continue
                kept.append(int(index))
            results = []
            query_tokens = set(tokens)
            for index in kept:
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


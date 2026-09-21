#!/usr/bin/env python3
"""FastAPI backend server for tech-db Q&A system.

Hybrid retrieval: BM25 (keyword) + vector (semantic) fused via RRF.
GLM-5.2 streaming for answer generation.

Endpoints:
  POST /api/chat/stream  - Streaming chat (SSE)
  GET  /api/graph       - Get knowledge graph data for visualization
  GET  /api/stats       - System statistics
  GET  /api/health      - Health check
  GET  /api/search       - Direct search (debug)

Run:
  .venv/bin/python qa-backend/server.py
"""
import os
import sys
import json
import pickle
import asyncio
import re
import secrets
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

# Add paths
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from config import (
    WORKING_DIR, llm_model_func, embedding_func,
    llm_stream_func, MODEL_NAME, LLM_CONFIGURED,
)
from incremental_index import IncrementalIndex

REPO = Path(__file__).resolve().parent.parent
LITE_PATH = REPO / "data" / "processed" / "all-records-lite.json"
INDEX_FILE = WORKING_DIR / "vector_index_v2.pkl"
BM25_FILE = WORKING_DIR / "bm25_index.pkl"
INCREMENTAL_INDEX_FILE = Path(
    os.getenv("TECHDB_QA_INCREMENTAL_INDEX_PATH", str(WORKING_DIR / "incremental" / "index.pkl"))
)
JIEBA_DICT = WORKING_DIR / "jieba_custom_dict.txt"

# ── Global state ──
_vector_index = None  # numpy array (N, 1024)
_index_meta = None    # list of metadata dicts
_bm25_index = None    # BM25Okapi instance
_bm25_meta = None     # BM25 metadata list
_bm25_corpus = None   # tokenized corpus for BM25
_records = None       # full records from all-records-lite.json
_index_mapping_status = None
_incremental_index = IncrementalIndex(INCREMENTAL_INDEX_FILE, embedding_func)

# ── RRF parameters ──
RRF_K = 60          # RRF constant (1/(rank+k))
RETRIEVAL_TOP_K = 50  # candidates per route
FINAL_TOP_K = 25     # max records after fusion
RELEVANCE_FLOOR = 0.3  # vector similarity floor for "honest answer" trigger

# Generic follow-up language adds noise to BM25 and can overpower the domain
# terms in short queries. Keep compact domain atoms because jieba sometimes
# segments Chinese technical names into one-character tokens.
BM25_STOPWORDS = {
    "请", "请问", "问", "回答", "答复", "介绍", "说明", "解释", "分析", "概述",
    "详细", "具体", "简单", "展开", "继续", "补充", "深入", "一下", "现在", "目前",
    "前面", "刚才", "这些", "那些", "上述", "其中", "这个", "那个", "相关", "主要",
    "什么", "怎么", "如何", "为什么", "是否", "能否", "可以", "能够", "帮我", "告诉",
    "内容", "问题", "信息", "资料", "数据", "数据库", "检索", "搜索", "结果", "第一波", "第二波",
}
BM25_SINGLE_CHAR_KEEP = {"钠", "锂", "硅", "碳", "氢", "氧", "氮", "氨", "钙", "钾", "铝", "镁"}


def _bm25_query_tokens(query: str) -> list[str]:
    import jieba

    tokens: list[str] = []
    seen: set[str] = set()
    for raw in jieba.cut_for_search(query):
        token = str(raw).strip().lower()
        if not token or token in BM25_STOPWORDS or re.fullmatch(r"[\W_]+", token, flags=re.UNICODE):
            continue
        if len(token) == 1 and token not in BM25_SINGLE_CHAR_KEEP and not token.isascii():
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def load_vector_index():
    """Load the pre-built vector index."""
    global _vector_index, _index_meta
    if _vector_index is not None:
        return
    # Try v2 first, fall back to v1
    idx_file = INDEX_FILE if INDEX_FILE.exists() else WORKING_DIR / "vector_index.pkl"
    if idx_file.exists():
        print(f"[startup] Loading vector index from {idx_file.name}...", flush=True)
        with open(idx_file, "rb") as f:
            data = pickle.load(f)
        _vector_index = data["embeddings"]
        _index_meta = data["meta"]
        print(f"[startup] Vector index loaded: {len(_index_meta)} records, dim={data['dim']}", flush=True)
    else:
        print(f"[startup] WARNING: No vector index found", flush=True)


def load_bm25_index():
    """Load the pre-built BM25 index."""
    global _bm25_index, _bm25_meta, _bm25_corpus
    if _bm25_index is not None:
        return
    if BM25_FILE.exists():
        print(f"[startup] Loading BM25 index...", flush=True)
        with open(BM25_FILE, "rb") as f:
            data = pickle.load(f)
        _bm25_index = data["bm25"]
        _bm25_meta = data["meta"]
        _bm25_corpus = data.get("corpus_tokens")
        print(f"[startup] BM25 index loaded: {len(_bm25_meta)} documents", flush=True)
    else:
        print(f"[startup] BM25 index not found (hybrid search disabled)", flush=True)


def load_records():
    """Load all-records-lite.json for full record lookup."""
    global _records
    if _records is None:
        _records = json.loads(LITE_PATH.read_text("utf-8"))
    return _records


def _mapping_key(record: dict, fields: tuple[str, ...]) -> tuple:
    """Build a stable, hashable key from index metadata and lite records."""
    values = []
    for field in fields:
        value = record.get(field, "")
        if isinstance(value, bool):
            pass
        elif isinstance(value, (int, float)):
            value = float(value)
        elif isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        values.append(value)
    return tuple(values)


def _remap_metadata(meta_items: list[dict], fields: tuple[str, ...], label: str) -> dict:
    """Remap stale array positions without rebuilding the existing index."""
    records = load_records()
    candidates = defaultdict(list)
    for record_idx, record in enumerate(records):
        candidates[_mapping_key(record, fields)].append(record_idx)

    occurrences = defaultdict(int)
    changed = 0
    ambiguous = 0
    missing = []
    for meta in meta_items:
        key = _mapping_key(meta, fields)
        matches = candidates.get(key, [])
        if not matches:
            missing.append({field: meta.get(field, "") for field in fields})
            continue
        if len(matches) > 1:
            ambiguous += 1
        occurrence = occurrences[key]
        mapped_idx = matches[min(occurrence, len(matches) - 1)]
        occurrences[key] += 1
        if meta.get("idx") != mapped_idx:
            changed += 1
        meta["idx"] = mapped_idx

    if missing:
        sample = json.dumps(missing[:3], ensure_ascii=False)
        raise RuntimeError(
            f"{label} metadata cannot be mapped to all-records-lite.json: "
            f"{len(missing)} missing; sample={sample}"
        )

    return {
        "records": len(meta_items),
        "changed": changed,
        "ambiguous": ambiguous,
        "key_fields": list(fields),
    }


def remap_index_metadata():
    """Align packaged indexes with the record order rebuilt from JS shards."""
    global _index_mapping_status
    status = {}
    if _index_meta is not None:
        status["vector"] = _remap_metadata(
            _index_meta,
            ("u", "t", "d", "c", "tg"),
            "vector index",
        )
    if _bm25_meta is not None:
        status["bm25"] = _remap_metadata(
            _bm25_meta,
            ("t", "d", "c"),
            "BM25 index",
        )
    _index_mapping_status = status
    return status


async def vector_search(query: str, top_k: int = RETRIEVAL_TOP_K) -> list:
    """Search the vector index for the most similar records."""
    if _vector_index is None and not _incremental_index.record_count:
        return []

    # Embed the query
    query_emb = await embedding_func([query])
    query_vec = np.array(query_emb[0], dtype=np.float32)
    query_vec = query_vec / max(np.linalg.norm(query_vec), 1e-8)

    results = []
    if _vector_index is not None:
        # Cosine similarity (embeddings are pre-normalized)
        scores = _vector_index @ query_vec
        top_indices = np.argsort(scores)[::-1][:top_k]
        results.extend(
            {"meta": _index_meta[int(idx)], "score": float(scores[int(idx)])}
            for idx in top_indices
        )
    results.extend(_incremental_index.vector_search(query_vec, top_k))
    return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]


def bm25_search(query: str, top_k: int = RETRIEVAL_TOP_K) -> list:
    """Search the BM25 index for keyword matches."""
    tokens = _bm25_query_tokens(query)
    if not tokens and _bm25_index is None:
        return []

    base_results = []
    if _bm25_index is not None and tokens:
        scores = _bm25_index.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        base_results.extend(
            {"meta": _bm25_meta[int(idx)], "score": float(scores[int(idx)])}
            for idx in top_indices
            if float(scores[int(idx)]) > 0
        )
    incremental_results = _incremental_index.bm25_search(" ".join(tokens), top_k) if tokens else []
    # BM25 scores from separately built corpora are not numerically comparable.
    # Interleave their ranked lists before the outer RRF fusion.
    results = []
    for rank in range(max(len(base_results), len(incremental_results))):
        if rank < len(base_results):
            results.append(base_results[rank])
        if rank < len(incremental_results):
            results.append(incremental_results[rank])
        if len(results) >= top_k:
            break
    return results[:top_k]


def rrf_fuse(vec_results: list, bm25_results: list,
             k: int = RRF_K, top_k: int = FINAL_TOP_K) -> list:
    """Reciprocal Rank Fusion of vector and BM25 results.

    Returns unified list of {meta, score} with RRF scores.
    """
    rrf_scores = {}  # record_idx -> {rrf, meta, vec_score, bm25_score}

    def result_key(result: dict) -> str:
        meta = result["meta"]
        return str(meta.get("key", f"base:{meta.get('idx', '')}"))

    for rank, result in enumerate(vec_results):
        rec_idx = result_key(result)
        if rec_idx not in rrf_scores:
            rrf_scores[rec_idx] = {"rrf": 0.0, "meta": result["meta"],
                                   "vec_score": 0.0, "bm25_score": 0.0}
        rrf_scores[rec_idx]["rrf"] += 1.0 / (rank + k)
        rrf_scores[rec_idx]["vec_score"] = result["score"]

    for rank, result in enumerate(bm25_results):
        rec_idx = result_key(result)
        if rec_idx not in rrf_scores:
            rrf_scores[rec_idx] = {"rrf": 0.0, "meta": result["meta"],
                                   "vec_score": 0.0, "bm25_score": 0.0}
        rrf_scores[rec_idx]["rrf"] += 1.0 / (rank + k)
        rrf_scores[rec_idx]["bm25_score"] = result["score"]

    # Sort by RRF score
    fused = sorted(rrf_scores.values(), key=lambda x: -x["rrf"])[:top_k]

    return [{
        "meta": item["meta"],
        "score": item["rrf"],
        "vec_score": item["vec_score"],
        "bm25_score": item["bm25_score"],
    } for item in fused]


async def hybrid_search(query: str) -> tuple:
    """Hybrid retrieval: vector + BM25 → RRF fusion → dynamic cutoff.

    Returns (search_results, is_relevant) where is_relevant indicates
    whether results are good enough to generate an answer.
    """
    # Run both routes in parallel
    vec_task = vector_search(query, top_k=RETRIEVAL_TOP_K)
    bm25_task = asyncio.to_thread(bm25_search, query, RETRIEVAL_TOP_K)

    vec_results, bm25_results = await asyncio.gather(vec_task, bm25_task)

    # If BM25 not available, just use vector
    if not bm25_results:
        results = vec_results[:FINAL_TOP_K]
    else:
        results = rrf_fuse(vec_results, bm25_results)

    # Dynamic cutoff: check if best result is relevant enough
    is_relevant = False
    if results:
        best_vec_score = max((r.get("vec_score", 0) for r in results), default=0)
        has_bm25_hit = any(r.get("bm25_score", 0) > 0 for r in results)
        # Relevant if vector score is decent OR BM25 found something
        is_relevant = best_vec_score >= RELEVANCE_FLOOR or has_bm25_hit

    results, _dropped = dedup_search_results(results)
    return results, is_relevant


def dedup_search_results(results: list) -> tuple:
    """Collapse near-duplicate records before context building.

    Same article ingested in different pipeline batches ends up as distinct
    record_idx entries with identical title/date/source/url (and uploads have
    one entry per chunk). Keeps the first (highest-scored) entry per
    record identity: record_id → url → (title|date|source). Ported from
    tech-db qa-backend/server.py (2026-09-20 retrieval dedup).

    Returns (deduped_results, dropped_count).
    """
    if not results:
        return results, 0

    records = load_records()

    def _resolve(result: dict) -> tuple:
        meta = result.get("meta") or {}
        rid = str(meta.get("record_id", "") or "")
        if meta.get("kind") == "upload":
            # uploads are chunk-level; dedupe by document so one doc keeps
            # only its best chunk
            return f"doc:{meta.get('document_id', rid or meta.get('idx', ''))}", meta
        orig_idx = meta.get("idx", -1)
        record = records[orig_idx] if isinstance(orig_idx, int) and 0 <= orig_idx < len(records) else {}
        title = " ".join(str(record.get("t", "") or "").split()).strip()
        date = str(record.get("d", "") or "").strip()
        source = str(record.get("a", record.get("s", "")) or "").strip()
        url = str(record.get("u", "") or "").strip()
        return "", (record or {}) | {"__title": title, "__date": date, "__source": source, "__url": url, "__rid": rid}

    seen: set = set()
    out = []
    dropped = 0
    for r in results:
        rid_or_doc, info = _resolve(r)
        if rid_or_doc:
            key = rid_or_doc
        else:
            title, date = info["__title"], info["__date"]
            source, url = info["__source"], info["__url"]
            if url:
                key = f"url:{url}"
            elif title:
                key = f"art:{title[:80]}|{date}|{source[:40]}"
            else:
                key = f"idx:{(r.get('meta') or {}).get('idx', len(seen))}"
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(r)
    return out, dropped


def build_context(search_results: list) -> tuple:
    """Build context string and citations from search results."""
    records = load_records()
    citations = []
    context_parts = []

    for i, result in enumerate(search_results):
        meta = result["meta"]
        score = result["score"]
        if meta.get("kind") == "upload":
            orig_idx = meta.get("document_id", "")
            record = meta
        else:
            orig_idx = meta.get("idx", -1)
            record = records[orig_idx] if 0 <= orig_idx < len(records) else None
        if not record:
            continue

        title = record.get("t", "") or ""
        date = record.get("d", "") or ""
        source = record.get("a", record.get("s", "")) or ""
        body = record.get("b", "") or record.get("fb", "") or ""
        ai_summary = record.get("as", "") or ""
        cat = record.get("c", "") or ""
        tags = record.get("tg", [])
        if isinstance(tags, str):
            tags = [tags]
        url = record.get("u", "") or ""
        sc = record.get("sc", 0)

        # Add to context
        context_parts.append(
            f"[{i+1}] [{cat}] {title} ({date})\n"
            f"来源: {source}\n"
            f"摘要: {body if record.get('kind') == 'upload' else (ai_summary[:300] if ai_summary else body[:300])}\n"
            f"相似度: {score:.2f}"
        )

        # Preserve uploaded document provenance; baseline citation shape is unchanged.
        upload_provenance = {}
        if record.get("kind") == "upload":
            upload_provenance = {"document_id": record.get("document_id"),
                                 "chunk_id": record.get("chunk_id"),
                                 "chunk_text": body,
                                 "chunk_metadata": record.get("chunk_metadata", {})}
        # Add citation
        citations.append({
            "id": i + 1,
            "record_id": orig_idx,
            "title": title,
            "date": date,
            "source": source,
            "score": sc,
            "tag": tags[0] if tags else "",
            "category": cat,
            "url": url,
            "body_snippet": (body[:200] if body else (ai_summary[:200] if ai_summary else "")),
            "similarity": round(score, 3),
            **upload_provenance,
        })

    context = "\n\n---\n\n".join(context_parts)
    return context, citations


# ── Request Models ──
class ChatRequest(BaseModel):
    query: str
    conversation_id: str = ""
    history: list = []


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_records()
    print(f"[startup] Records loaded: {len(_records)}", flush=True)
    print("[startup] Loading vector index...", flush=True)
    load_vector_index()
    print("[startup] Loading BM25 index...", flush=True)
    load_bm25_index()

    mapping_status = remap_index_metadata()
    print(f"[startup] Index metadata mapped: {mapping_status}", flush=True)
    _incremental_index.load()

    # Load jieba custom dictionary for query tokenization
    if JIEBA_DICT.exists():
        import jieba
        jieba.load_userdict(str(JIEBA_DICT))
        print("[startup] Jieba custom dict loaded", flush=True)

    print("[startup] Ready!", flush=True)
    yield
    print("[shutdown] Cleaning up...", flush=True)


# ── FastAPI App ──
app = FastAPI(title="Tech-DB Q&A API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ──

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "llm_configured": LLM_CONFIGURED,
        "vector_index_ready": _vector_index is not None,
        "bm25_ready": _bm25_index is not None,
        "indexed_records": len(_index_meta) if _index_meta else 0,
        "bm25_records": len(_bm25_meta) if _bm25_meta else 0,
        "incremental_index_ready": _incremental_index.loaded,
        "incremental_records": _incremental_index.record_count,
        "incremental_documents": _incremental_index.document_count,
        "total_indexed_records": (len(_index_meta) if _index_meta else 0) + _incremental_index.record_count,
        "total_records": len(_records) if _records else 0,
        "index_mapping_ready": _index_mapping_status is not None,
        "index_mapping": _index_mapping_status or {},
        "time": datetime.now().isoformat(),
    }


class IndexChunk(BaseModel):
    chunk_id: str = ""
    text: str
    metadata: dict = Field(default_factory=dict)


class IndexUpsertRequest(BaseModel):
    document_id: str
    filename: str = ""
    title: str = ""
    primary_category: str = "未分类"
    secondary_categories: list[str] = Field(default_factory=list)
    confidentiality: str | None = None
    source_type: str | None = None
    checksum_sha256: str | None = None
    created_at: str | None = None
    chunks: list[IndexChunk]


def _check_index_token(token: str | None) -> None:
    expected = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    if expected and not secrets.compare_digest(token or "", expected):
        raise HTTPException(status_code=401, detail="invalid index token")


@app.post("/api/index/upsert")
async def index_upsert(
    req: IndexUpsertRequest,
    x_techdb_index_token: str | None = Header(default=None),
):
    """Embed and persist one uploaded document in the incremental index."""
    _check_index_token(x_techdb_index_token)
    try:
        result = await _incremental_index.upsert(
            document_id=req.document_id,
            filename=req.filename,
            title=req.title,
            primary_category=req.primary_category,
            secondary_categories=req.secondary_categories,
            confidentiality=req.confidentiality,
            source_type=req.source_type,
            checksum_sha256=req.checksum_sha256,
            created_at=req.created_at,
            chunks=[chunk.model_dump() for chunk in req.chunks],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[index] upsert failed for {req.document_id}: {exc}", flush=True)
        raise HTTPException(status_code=503, detail="embedding index is unavailable") from exc
    return {"status": "ready", **result}


class IndexDeleteRequest(BaseModel):
    document_id: str = Field(min_length=1)


@app.post("/api/index/delete")
async def index_delete(
    req: IndexDeleteRequest,
    x_techdb_index_token: str | None = Header(default=None),
):
    """Remove one uploaded document from the incremental index (idempotent)."""
    _check_index_token(x_techdb_index_token)
    try:
        removed = await _incremental_index.remove_document(req.document_id)
    except Exception as exc:
        print(f"[index] delete failed for {req.document_id}: {exc}", flush=True)
        raise HTTPException(status_code=503, detail="embedding index is unavailable") from exc
    return {"status": "ok", "document_id": req.document_id, "removed_chunks": removed}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat endpoint using SSE."""

    async def event_generator():
        try:
            # Step 1: Retrieval
            yield {"event": "status", "data": json.dumps({
                "step": "retrieving",
                "message": "正在检索相关知识..."
            })}

            if _vector_index is None and not _incremental_index.record_count:
                yield {"event": "error", "data": json.dumps({
                    "message": "向量索引尚未构建。请运行: python qa-backend/vector_index.py"
                })}
                return

            # Hybrid search (vector + BM25 → RRF)
            search_results, is_relevant = await hybrid_search(req.query)

            if not search_results or not is_relevant:
                yield {"event": "done", "data": json.dumps({
                    "answer": "抱歉，数据库中没有足够的情报来回答这个问题。请尝试用更具体的关键词或换个角度提问。",
                    "citations": []
                })}
                return

            # Build context and citations
            context, citations = build_context(search_results)

            # Yield citations
            if citations:
                yield {"event": "citations", "data": json.dumps({"citations": citations})}

            # Step 2: Analysis
            yield {"event": "status", "data": json.dumps({
                "step": "analyzing",
                "message": f"找到 {len(citations)} 条相关记录，正在分析..."
            })}

            await asyncio.sleep(0.1)  # Small delay for UX

            # Step 3: Generation
            yield {"event": "status", "data": json.dumps({
                "step": "generating",
                "message": "正在生成回答..."
            })}

            # Build source list for prompt
            source_list = "\n".join(
                f"[{i+1}] {c['title']} ({c['date']}, {c['source']})"
                for i, c in enumerate(citations)
            )

            system_prompt = f"""你是技术情报分析专家。基于以下检索到的技术情报资料回答用户问题。

要求：
1. 只基于提供的资料回答，不要编造信息
2. 在回答中用 [1][2] 等标注引用来源（对应来源列表的序号）
3. 如果资料中没有相关信息，诚实回答"数据库中没有相关信息"
4. 简单问题简短回答，复杂问题详细分析
5. 使用中文回答，使用markdown格式

检索到的资料：
{context}

来源列表：
{source_list}"""

            # Build conversation history for LLM
            llm_history = []
            for msg in req.history[-6:]:
                llm_history.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })

            full_answer = ""
            try:
                # Stream directly from LLM
                async for chunk in llm_stream_func(
                    prompt=req.query,
                    system_prompt=system_prompt,
                    history_messages=llm_history,
                ):
                    if chunk:
                        full_answer += chunk
                        yield {"event": "token", "data": json.dumps({"text": chunk})}
            except Exception as e:
                # Fallback: non-streaming
                print(f"[stream-fallback] {e}", flush=True)
                try:
                    answer = await llm_model_func(
                        req.query,
                        system_prompt=system_prompt,
                        history_messages=llm_history,
                    )
                    if answer:
                        full_answer = answer
                        for i in range(0, len(answer), 3):
                            yield {"event": "token", "data": json.dumps({"text": answer[i:i+3]})}
                            await asyncio.sleep(0.015)
                except Exception as e2:
                    yield {"event": "error", "data": json.dumps({
                        "message": f"生成失败: {e2}"
                    })}
                    return

            yield {"event": "done", "data": json.dumps({
                "answer": full_answer,
                "citations": citations
            })}

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_generator())


@app.get("/api/graph")
async def get_graph(limit: int = 300):
    """Get knowledge graph data for visualization."""
    graph_file = WORKING_DIR / "graph-export.json"
    if graph_file.exists():
        data = json.loads(graph_file.read_text("utf-8"))
        nodes = sorted(data.get("nodes", []), key=lambda n: n.get("degree", 0), reverse=True)
        if limit and len(nodes) > limit:
            top_node_ids = {n["id"] for n in nodes[:limit]}
            nodes = nodes[:limit]
            edges = [e for e in data.get("edges", [])
                     if e["source"] in top_node_ids and e["target"] in top_node_ids]
        else:
            edges = data.get("edges", [])
        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(data.get("nodes", [])),
            "total_edges": len(data.get("edges", [])),
        }
    return {
        "nodes": [],
        "edges": [],
        "total_nodes": 0,
        "total_edges": 0,
        "message": "Graph not yet built."
    }


@app.get("/api/stats")
async def stats():
    """Get system statistics."""
    total = len(_records) if _records else 0
    indexed = len(_index_meta) if _index_meta else 0

    graph_file = WORKING_DIR / "graph-export.json"
    nodes = edges = 0
    if graph_file.exists():
        graph = json.loads(graph_file.read_text("utf-8"))
        nodes = len(graph.get("nodes", []))
        edges = len(graph.get("edges", []))

    return {
        "total_records": total,
        "indexed_records": indexed,
        "bm25_records": len(_bm25_meta) if _bm25_meta else 0,
        "incremental_index_ready": _incremental_index.loaded,
        "incremental_records": _incremental_index.record_count,
        "incremental_documents": _incremental_index.document_count,
        "total_indexed_records": indexed + _incremental_index.record_count,
        "graph_nodes": nodes,
        "graph_edges": edges,
        "vector_index_ready": _vector_index is not None,
        "bm25_ready": _bm25_index is not None,
        "index_mapping_ready": _index_mapping_status is not None,
        "index_mapping": _index_mapping_status or {},
        "model": MODEL_NAME,
        "llm_configured": LLM_CONFIGURED,
    }


@app.get("/api/search")
async def search(q: str, top_k: int = 10):
    """Quick vector search without LLM generation. Returns matching records."""
    if _vector_index is None and not _incremental_index.record_count:
        return JSONResponse(
            {"error": "Vector index not loaded", "results": []},
            status_code=503,
        )
    if not q.strip():
        return {"results": [], "query": q}

    results, is_relevant = await hybrid_search(q.strip())
    context, citations = build_context(results[:min(max(top_k, 1), 50)])
    return {
        "query": q,
        "results": citations,
        "total": len(citations),
        "is_relevant": is_relevant,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)


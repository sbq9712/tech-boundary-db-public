"""Adapter for the canonical retrieval API shipped with sbq9712/tech-db.

The portal owns authentication, conversations and answer generation.  This
adapter only consumes the upstream hybrid-search, stats and graph contracts.
No fallback index is built locally: absent assets or service configuration are
reported explicitly so deployment cannot silently switch knowledge sources.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


REQUIRED_QA_ASSETS = (
    "vector_index_v2.pkl (or vector_index.pkl)",
    "bm25_index.pkl",
    "jieba_custom_dict.txt",
    "all-records-lite.json",
    "bge-m3 model directory",
    "qa-assets-manifest.json",
)


@dataclass(slots=True)
class QAServiceError(RuntimeError):
    code: str
    public_message: str
    detail: str = ""

    def __str__(self) -> str:
        return self.public_message


def qa_service_url() -> str:
    return os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")


def qa_service_timeout() -> float:
    raw = os.getenv("TECHDB_QA_SERVICE_TIMEOUT_SECONDS", "120").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 120.0


def _require_url() -> str:
    base_url = qa_service_url()
    if not base_url:
        raise QAServiceError(
            code="qa_service_unconfigured",
            public_message="检索服务未配置，请在服务器部署时挂载既有模型与索引资产。",
        )
    return base_url


def _service_error(exc: Exception) -> QAServiceError:
    if isinstance(exc, QAServiceError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return QAServiceError("qa_service_timeout", "检索服务响应超时，请稍后重试。", str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        code = "qa_assets_unavailable" if exc.response.status_code == 503 else "qa_service_error"
        message = "检索索引尚未就绪，请确认既有向量与 BM25 资产已挂载。" if code == "qa_assets_unavailable" else "检索服务暂时不可用，请稍后重试。"
        return QAServiceError(code, message, f"HTTP {exc.response.status_code}")
    if isinstance(exc, httpx.RequestError):
        return QAServiceError("qa_service_unreachable", "无法连接检索服务，请检查服务配置。", str(exc))
    return QAServiceError("qa_service_error", "检索服务返回异常，请稍后重试。", str(exc))


async def search_canonical(
    query: str,
    top_k: int = 25,
    exclude_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return upstream citation-shaped results from the canonical hybrid index.

    exclude_ids：历史轮已引用记录 ID（novelty exclusion），追问不重复召回。
    """
    payload = await search_canonical_raw(query, top_k=top_k, exclude_ids=exclude_ids)
    if payload.get("is_relevant") is False:
        return []
    return [item for item in payload["results"] if isinstance(item, dict)]


async def search_canonical_raw(
    query: str,
    top_k: int = 25,
    exclude_ids: list[str] | None = None,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """检索原始载荷：citations 之外还带 evidence/retrieval_trace（编排层评估）。

    旧版 canonical-qa（无编排层）不返回这两个键，兼容降级为 {}。
    sources（任务二 2.2）：来源子集（breadth/industry/atsc）——None=默认
    三源全开；显式收窄时透传（用户/入口限定作用域，不静默丢源）。
    """
    base_url = _require_url()
    params: dict[str, Any] = {"q": query, "top_k": min(max(top_k, 1), 50)}
    novelty = [str(x).strip() for x in (exclude_ids or []) if str(x).strip()][:80]
    if novelty:
        params["exclude_ids"] = ",".join(novelty)
    valid_sources = tuple(
        str(x).strip().lower() for x in (sources or [])
        if str(x).strip().lower() in ("breadth", "industry", "atsc"))
    if valid_sources:
        params["sources"] = ",".join(valid_sources)
    try:
        async with httpx.AsyncClient(timeout=qa_service_timeout()) as client:
            response = await client.get(f"{base_url}/api/search", params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, QAServiceError) as exc:
        raise _service_error(exc) from exc

    if payload.get("error"):
        raise QAServiceError("qa_assets_unavailable", "检索索引尚未就绪，请确认既有向量与 BM25 资产已挂载。", str(payload.get("error")))
    results = payload.get("results")
    if not isinstance(results, list):
        raise QAServiceError("qa_contract_error", "检索服务响应格式不兼容。")
    return payload


async def service_status() -> dict[str, Any]:
    base_url = qa_service_url()
    base = {
        "configured": bool(base_url),
        "ready": False,
        "provider": "sbq9712/tech-db canonical hybrid retrieval",
        "required_assets": list(REQUIRED_QA_ASSETS),
    }
    if not base_url:
        return {**base, "status": "unconfigured", "message": "检索服务未配置"}
    try:
        async with httpx.AsyncClient(timeout=min(qa_service_timeout(), 8.0)) as client:
            health_response, stats_response = await client.get(f"{base_url}/api/health"), await client.get(f"{base_url}/api/stats")
            health_response.raise_for_status()
            stats_response.raise_for_status()
            health = health_response.json()
            stats = stats_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        error = _service_error(exc)
        return {**base, "status": "error", "message": error.public_message, "code": error.code}

    ready = (
        bool(health.get("vector_index_ready"))
        and bool(health.get("bm25_ready"))
        and bool(health.get("index_mapping_ready"))
    )
    return {
        **base,
        "status": "ok" if ready else "assets_missing",
        "ready": ready,
        "message": "检索服务已就绪" if ready else "检索服务已连接，但索引资产未就绪",
        "stats": {
            "total_records": stats.get("total_records", health.get("total_records", 0)),
            "indexed_records": stats.get("indexed_records", health.get("indexed_records", 0)),
            "bm25_records": stats.get("bm25_records", health.get("bm25_records", 0)),
            "incremental_index_ready": health.get("incremental_index_ready", False),
            "incremental_records": stats.get("incremental_records", health.get("incremental_records", 0)),
            "incremental_documents": stats.get("incremental_documents", health.get("incremental_documents", 0)),
            "total_indexed_records": stats.get("total_indexed_records", health.get("total_indexed_records", 0)),
            "graph_nodes": stats.get("graph_nodes", 0),
            "graph_edges": stats.get("graph_edges", 0),
            "vector_index_ready": health.get("vector_index_ready", False),
            "bm25_ready": health.get("bm25_ready", False),
            "index_mapping_ready": health.get("index_mapping_ready", False),
            "index_mapping": health.get("index_mapping", {}),
        },
    }


async def graph_snapshot(limit: int = 200, scope: str = "breadth") -> dict[str, Any]:
    """门户背景图谱（任务二 2.4）：默认 scope=breadth——服务端已按来源
    过滤（度数/标签/计数不含行业/ATSC 贡献）；行业/ATSC 图谱只服务各自
    栏目检索，不进门户背景。"""
    base_url = _require_url()
    scope = scope if scope in ("breadth", "industry", "atsc") else "breadth"
    try:
        async with httpx.AsyncClient(timeout=qa_service_timeout()) as client:
            response = await client.get(f"{base_url}/api/graph", params={
                "limit": min(max(limit, 1), 500), "scope": scope})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, QAServiceError) as exc:
        raise _service_error(exc) from exc
    if not isinstance(payload.get("nodes", []), list) or not isinstance(payload.get("edges", []), list):
        raise QAServiceError("qa_contract_error", "图谱服务响应格式不兼容。")
    return {"nodes": payload.get("nodes", []), "edges": payload.get("edges", [])}

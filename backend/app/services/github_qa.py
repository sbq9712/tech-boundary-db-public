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


async def search_canonical(query: str, top_k: int = 25) -> list[dict[str, Any]]:
    """Return upstream citation-shaped results from the canonical hybrid index."""
    base_url = _require_url()
    try:
        async with httpx.AsyncClient(timeout=qa_service_timeout()) as client:
            response = await client.get(
                f"{base_url}/api/search",
                params={"q": query, "top_k": min(max(top_k, 1), 50)},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, QAServiceError) as exc:
        raise _service_error(exc) from exc

    if payload.get("error"):
        raise QAServiceError("qa_assets_unavailable", "检索索引尚未就绪，请确认既有向量与 BM25 资产已挂载。", str(payload.get("error")))
    results = payload.get("results")
    if not isinstance(results, list):
        raise QAServiceError("qa_contract_error", "检索服务响应格式不兼容。")
    # A low-confidence lexical/vector hit should not become answer evidence.
    # Older canonical services omit this field, so preserve compatibility.
    if payload.get("is_relevant") is False:
        return []
    return [item for item in results if isinstance(item, dict)]


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


async def graph_snapshot(limit: int = 200) -> dict[str, Any]:
    base_url = _require_url()
    try:
        async with httpx.AsyncClient(timeout=qa_service_timeout()) as client:
            response = await client.get(f"{base_url}/api/graph", params={"limit": min(max(limit, 1), 500)})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, QAServiceError) as exc:
        raise _service_error(exc) from exc
    if not isinstance(payload.get("nodes", []), list) or not isinstance(payload.get("edges", []), list):
        raise QAServiceError("qa_contract_error", "图谱服务响应格式不兼容。")
    return {"nodes": payload.get("nodes", []), "edges": payload.get("edges", [])}

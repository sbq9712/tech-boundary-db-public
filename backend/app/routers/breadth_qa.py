"""广度页面「数据库问答」视图的认证代理（TagDB 完整接入收口）。

tech-db 原生 qa.js 直连 qa-backend :8765（无鉴权）。本仓部署形态下
canonical-qa 仅内网可达（compose 内部网络 + 127.0.0.1 绑定），广度页面
iframe 与门户同源，故经 api 服务加 Bearer 鉴权后转发，保持一条问答链路：

    breadth/qa.js → /api/breadth/qa/chat/stream → canonical-qa /api/chat/stream
                                      /api/breadth/qa/graph   → canonical-qa /api/graph
                                      /api/breadth/qa/stats   → canonical-qa /api/stats

SSE 逐块转发（不做整包缓冲），错误以 QAServiceError 的公开口径返回。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services.github_qa import _service_error, qa_service_timeout, qa_service_url

router = APIRouter(tags=["breadth"], dependencies=[Depends(get_current_user)])

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"




class BreadthQaChatIn(BaseModel):
    # 与 canonical-qa ChatRequest 对齐；多余字段拒收，保持显式契约
    query: str = Field(min_length=1, max_length=2000)
    conversation_id: str = ""
    history: list[dict[str, Any]] = []
    exclude_ids: list[str] = []


@router.post("/breadth/qa/chat/stream")
async def breadth_qa_chat_stream(payload: BreadthQaChatIn):
    base = qa_service_url()
    if not base:
        return JSONResponse(status_code=503, content={"detail": "检索服务未配置。"})

    upstream_body = payload.model_dump()

    async def relay():
        try:
            async with httpx.AsyncClient(timeout=qa_service_timeout()) as client:
                async with client.stream(
                    "POST", f"{base}/api/chat/stream", json=upstream_body
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")[:500]
                        yield _sse("error", {"message": f"上游检索服务错误（HTTP {resp.status_code}）：{body}"})
                        return
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except httpx.HTTPError as exc:
            err = _service_error(exc)
            yield _sse("error", {"message": err.public_message})

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/breadth/qa/graph")
async def breadth_qa_graph(limit: int = 200) -> Any:
    base = qa_service_url()
    if not base:
        return JSONResponse(status_code=503, content={"detail": "检索服务未配置。"})
    try:
        async with httpx.AsyncClient(timeout=qa_service_timeout()) as client:
            resp = await client.get(
                f"{base}/api/graph", params={"limit": min(max(limit, 1), 500)}
            )
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        err = _service_error(exc)
        return JSONResponse(status_code=502, content={"detail": err.public_message})


@router.get("/breadth/qa/stats")
async def breadth_qa_stats() -> Any:
    base = qa_service_url()
    if not base:
        return JSONResponse(status_code=503, content={"detail": "检索服务未配置。"})
    try:
        async with httpx.AsyncClient(timeout=qa_service_timeout()) as client:
            resp = await client.get(f"{base}/api/stats")
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        err = _service_error(exc)
        return JSONResponse(status_code=502, content={"detail": err.public_message})

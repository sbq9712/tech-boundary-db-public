"""广度页面「数据库问答」视图的认证代理（TagDB 完整接入收口）。

tech-db 原生 qa.js 直连 qa-backend :8765（无鉴权）。本仓部署形态下
canonical-qa 仅内网可达（compose 内部网络 + 127.0.0.1 绑定），广度页面
iframe 与门户同源，故经 api 服务加 Bearer 鉴权后转发，保持一条问答链路：

    breadth/qa.js → /api/breadth/qa/chat/stream → canonical-qa /api/chat/stream
                                      /api/breadth/qa/graph   → canonical-qa /api/graph
                                      /api/breadth/qa/stats   → canonical-qa /api/stats

SSE 逐块转发（不做整包缓冲），错误以 QAServiceError 的公开口径返回。

安全收口（codex 审查 REQUEST_CHANGES 落实）：
- 上游非 200 / 断流时只回状态码与固定文案，绝不透传上游响应体（防内部路径/URL 泄露）。
- history 严格建模为 role/content（canonical-qa 只消费这两个字段，见 server.py llm_history
  构造），客户端附带的 cited_record_ids/searched_record_ids 等字段在代理层剥离，
  杜绝伪造 novelty 排除与载荷放大。
- exclude_ids（novelty 排除）限长 + 白名单字符校验。
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import get_current_user
from app.services.github_qa import _service_error, qa_service_timeout, qa_service_url

router = APIRouter(tags=["breadth"], dependencies=[Depends(get_current_user)])

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"




class _HistoryItem(BaseModel):
    """canonical-qa 只消费 role/content（llm_history 构造，server.py）。

    客户端历史里携带的 cited_record_ids / searched_record_ids 等扩展字段
    在代理层静默剥离：上游不读它们，透传只会给认证用户留下伪造
    novelty 排除与放大 LLM 上下文的面。extra="ignore" 同时兼容旧缓存 JS。
    """

    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


# novelty 排除 id：canonical-qa 接受 record_idx / document_id / url 三种形态。
# 紧凑形态（idx/document_id）用白名单；URL 形态单独校验——真实语料的 URL
# 含空格/Unicode/括号/波浪号（实测约 6,246 条），白名单字符集会拒绝它们，
# 导致带引用追问 422（codex 复审 R2-3）。
_EXCLUDE_ID_RE = re.compile(r"^[A-Za-z0-9_\-./:=?#@%]{1,512}$")


def _valid_exclude_id(s: str) -> bool:
    if not 1 <= len(s) <= 512:
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in s):  # 控制字符一律拒绝
        return False
    if _EXCLUDE_ID_RE.fullmatch(s):
        return True
    try:
        parts = urlsplit(s)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


class BreadthQaChatIn(BaseModel):
    # 与 canonical-qa ChatRequest 对齐；多余字段拒收，保持显式契约
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    conversation_id: str = Field(default="", max_length=128)
    history: list[_HistoryItem] = Field(default_factory=list, max_length=20)
    # record_idx 以 int 到达（citations[].record_id 原样回传），统一归一为 str：
    # 上游 novelty_filter 本就 `str(e)` 归一后比对。
    exclude_ids: list[str | int] = Field(default_factory=list, max_length=200)

    @field_validator("exclude_ids")
    @classmethod
    def _validate_exclude_ids(cls, value: list[str | int]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            if isinstance(item, bool):
                raise ValueError("exclude_ids 含非法布尔值")
            s = str(item)
            if not _valid_exclude_id(s):
                raise ValueError("exclude_ids 含非法值（仅允许 record_idx/document_id/http(s)-url 形态）")
            normalized.append(s)
        return normalized


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
                        # 不透传上游响应体：内部路径 / URL / 实现细节一律不出内网
                        yield _sse(
                            "error",
                            {"message": f"上游检索服务错误（HTTP {resp.status_code}），请稍后重试。"},
                        )
                        return
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except httpx.HTTPError as exc:
            err = _service_error(exc)
            # _service_error 输出的 public_message 为固定口径文案，不含上游原文
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

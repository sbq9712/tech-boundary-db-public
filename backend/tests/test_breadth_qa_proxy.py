"""广度页「数据库问答」认证代理：契约 + 鉴权 + SSE 透传 + 上游错误映射。

对应 codex 审查（2026-10-02 REQUEST_CHANGES）的修复验收：
- 三端点鉴权（chat/stream、graph、stats）
- 任意 chunk 切分下的 SSE 字节级透传（含多字节 UTF-8 被切断的场景）
- 上游错误不透传响应体
- history 严格契约（剥离扩展字段、限界）
- exclude_ids 归一与白名单校验
前端解析侧（sseFrameParser/handleSSEData）见 tests/js/test_qa_sse_parser.mjs。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.routers.breadth_qa import BreadthQaChatIn


@pytest.fixture()
def client():
    return TestClient(app)


def _auth(client) -> dict:
    from app.core.security import create_token
    token = create_token("breadthqa-test")
    return {"Authorization": f"Bearer {token}"}


def test_requires_auth(client):
    """三个端点都必须持有效 Bearer token（路由级 Depends(get_current_user)）。"""
    assert client.get("/api/breadth/qa/stats").status_code == 401
    assert client.get("/api/breadth/qa/graph").status_code == 401
    with client.stream(
        "POST", "/api/breadth/qa/chat/stream",
        headers={"Content-Type": "application/json"},
        json={"query": "q"},
    ) as resp:
        assert resp.status_code == 401


def test_unconfigured_service_returns_503(client, monkeypatch):
    monkeypatch.delenv("TECHDB_QA_SERVICE_URL", raising=False)
    from app.services import github_qa
    monkeypatch.setattr(github_qa, "qa_service_url", lambda: "")
    resp = client.get("/api/breadth/qa/stats", headers=_auth(client))
    assert resp.status_code == 503


def test_stats_proxies_upstream(client, monkeypatch):
    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"total_records": 1, "indexed_records": 1}
    async def fake_get(self, url, **kw):
        assert url.endswith("/api/stats")
        return _Resp()
    from app.services import github_qa
    monkeypatch.setattr(github_qa, "qa_service_url", lambda: "http://qa")
    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    resp = client.get("/api/breadth/qa/stats", headers=_auth(client))
    assert resp.status_code == 200
    assert resp.json()["total_records"] == 1


def test_chat_stream_relays_sse_chunks(client, monkeypatch):
    from app.services import github_qa
    monkeypatch.setattr(github_qa, "qa_service_url", lambda: "http://qa")

    class _StreamCtx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        status_code = 200
        async def aiter_bytes(self):
            yield b'event: token\ndata: {"text": "hi"}\n\n'
            yield b'event: done\ndata: {"answer": "hi"}\n\n'

    calls = {}
    def fake_stream(self, method, url, **kw):
        calls['url'] = url
        calls['json'] = kw.get('json')
        return _StreamCtx()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    with client.stream(
        "POST", "/api/breadth/qa/chat/stream",
        headers={**_auth(client), "Content-Type": "application/json"},
        json={"query": "q"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b"".join(resp.iter_bytes()).decode()
    assert 'event: token' in body and 'event: done' in body
    assert calls['url'].endswith("/api/chat/stream")
    assert calls['json'] == {"query": "q", "conversation_id": "", "history": [], "exclude_ids": []}


def test_chat_stream_upstream_error_emits_sse_error(client, monkeypatch):
    """上游非 200：固定口径 error 事件，绝不透传上游响应体（防内部信息泄露）。"""
    from app.services import github_qa
    monkeypatch.setattr(github_qa, "qa_service_url", lambda: "http://qa")

    class _StreamCtx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        status_code = 500
        async def aiter_bytes(self):
            yield b"boom"
            return
        async def aread(self): return b"/app/qa-backend/internal/path boom"

    def fake_stream(self, method, url, **kw):
        return _StreamCtx()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    with client.stream(
        "POST", "/api/breadth/qa/chat/stream",
        headers={**_auth(client), "Content-Type": "application/json"},
        json={"query": "q"},
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode()
    assert "event: error" in body and "HTTP 500" in body
    # 上游响应体（含内部路径）不得出现在面向前端的流里
    assert "boom" not in body
    assert "/app/qa-backend" not in body


def test_chat_stream_relays_sse_chunks_split_mid_event(client, monkeypatch):
    """chunk 任意切分（切断 data: 行、切断多字节 UTF-8）下字节级透传。

    代理不做解析/重组，因此契约就是字节透明；重组责任在浏览器端
    sseFrameParser（见 tests/js/test_qa_sse_parser.mjs）。
    """
    from app.services import github_qa
    monkeypatch.setattr(github_qa, "qa_service_url", lambda: "http://qa")

    full = (
        'event: status\ndata: {"step": "retrieving", "message": "正在检索"}\n\n'
        'event: token\ndata: {"text": "固态电解质"}\n\n'
        'event: replace\ndata: {"content": "改写后的答案"}\n\n'
        'event: done\ndata: {"answer": "终稿", "citations": []}\n\n'
    ).encode("utf-8")

    # 硬切分：每 7 字节一块，必然出现 data: 行中途断裂与 UTF-8 多字节断裂
    chunks = [full[i:i + 7] for i in range(0, len(full), 7)]

    class _StreamCtx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        status_code = 200
        async def aiter_bytes(self):
            for c in chunks:
                yield c

    def fake_stream(self, method, url, **kw):
        return _StreamCtx()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    with client.stream(
        "POST", "/api/breadth/qa/chat/stream",
        headers={**_auth(client), "Content-Type": "application/json"},
        json={"query": "q"},
    ) as resp:
        body = b"".join(resp.iter_bytes())

    assert body == full, "代理破坏了 SSE 字节流（切分边界重组错误）"


def test_chat_stream_strips_history_extras(client, monkeypatch):
    """history 扩展字段（cited_record_ids 等）在代理层剥离，只留 role/content。"""
    from app.services import github_qa
    monkeypatch.setattr(github_qa, "qa_service_url", lambda: "http://qa")

    class _StreamCtx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        status_code = 200
        async def aiter_bytes(self):
            yield b'event: done\ndata: {"answer": "ok"}\n\n'

    captured = {}
    def fake_stream(self, method, url, **kw):
        captured["json"] = kw.get("json")
        return _StreamCtx()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    with client.stream(
        "POST", "/api/breadth/qa/chat/stream",
        headers={**_auth(client), "Content-Type": "application/json"},
        json={
            "query": "追问",
            "conversation_id": "c1",
            "history": [
                {"role": "user", "content": "一问"},
                {"role": "assistant", "content": "一答",
                 "cited_record_ids": [3, 7], "searched_record_ids": ["x"]},
            ],
            "exclude_ids": [3, 7, "upload-abc.txt"],
        },
    ) as resp:
        b"".join(resp.iter_bytes())

    assert captured["json"]["history"] == [
        {"role": "user", "content": "一问"},
        {"role": "assistant", "content": "一答"},
    ]
    # int idx 归一为 str（上游 novelty_filter 以 str 比对）
    assert captured["json"]["exclude_ids"] == ["3", "7", "upload-abc.txt"]


def test_payload_contract_history_bounds():
    with pytest.raises(ValidationError):
        BreadthQaChatIn(query="q", history=[{"role": "user", "content": "x"}] * 21)
    with pytest.raises(ValidationError):
        BreadthQaChatIn(query="q", history=[{"role": "user", "content": "x" * 8001}])
    with pytest.raises(ValidationError):
        BreadthQaChatIn(query="q", history=[{"role": "system", "content": "x"}])


def test_payload_contract_exclude_ids_validation():
    with pytest.raises(ValidationError):
        BreadthQaChatIn(query="q", exclude_ids=["a b"])        # 空白
    with pytest.raises(ValidationError):
        BreadthQaChatIn(query="q", exclude_ids=["a\";drop"])   # 引号注入载体
    with pytest.raises(ValidationError):
        BreadthQaChatIn(query="q", exclude_ids=[str(i) for i in range(201)])
    ok = BreadthQaChatIn(query="q", exclude_ids=[0, 12, "doc-id_1.txt"])
    assert ok.model_dump()["exclude_ids"] == ["0", "12", "doc-id_1.txt"]


def test_payload_contract_rejects_empty_query(client):
    with pytest.raises(Exception):
        BreadthQaChatIn(query="")
    with pytest.raises(ValidationError):
        BreadthQaChatIn(query="q", conversation_id="c" * 129)
    with pytest.raises(ValidationError):
        BreadthQaChatIn(query="q", unknown_field=1)           # extra=forbid
    ok = BreadthQaChatIn(query="q", conversation_id="c1", history=[], exclude_ids=[])
    assert ok.model_dump()["conversation_id"] == "c1"

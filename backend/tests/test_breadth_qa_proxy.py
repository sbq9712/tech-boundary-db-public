"""广度页「数据库问答」认证代理：契约 + 鉴权 + 上游错误映射。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

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
    resp = client.get("/api/breadth/qa/stats")
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
    from app.services import github_qa
    monkeypatch.setattr(github_qa, "qa_service_url", lambda: "http://qa")

    class _StreamCtx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        status_code = 500
        async def aiter_bytes(self):
            yield b"boom"
            return
        async def aread(self): return b"boom"

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


def test_payload_contract_rejects_empty_query(client):
    with pytest.raises(Exception):
        BreadthQaChatIn(query="")
    ok = BreadthQaChatIn(query="q", conversation_id="c1", history=[], exclude_ids=[])
    assert ok.model_dump()["conversation_id"] == "c1"

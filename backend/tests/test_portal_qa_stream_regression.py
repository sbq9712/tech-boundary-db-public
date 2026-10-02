"""任务二 2.1 回归测试：消费真实 ``stream_agent_response()`` 的门户问答主路径。

历史缺陷（本轮审查 2.1）：检索成功后 ``_retrieval_summary`` 重构把局部变量
``evidence`` 移入函数作用域，主路径仍引用 ``evidence.get(...)`` → NameError，
前端只看到流中断（network error），答案永不进入生成/核验阶段，run 停留
running。本文件按真实事件流逐项回归：

1. 有证据：完整走完 检索→分析→生成→核验→落库→done；
2. 无证据：弃权回答、run completed、无引用；
3. 检索错误：error 事件与落库 failed 一致；
4. 核验失败：答案仍下发（fail-open for answer）、状态如实降级（fail-closed）；
5. 内部异常（NameError 同类）：error 事件 + run 兜底定为 failed（绝不卡 running）；
6. summary 缺 evidence 键（旧检索服务兼容）：evidence_status=unknown，不抛错。

所有用例直接 async 消费生成器本体（非并行实现、非仅单测内部函数）。
"""

from __future__ import annotations

import json
import uuid

import pytest

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.conversation import (
    ConversationAgentRun,
    ConversationMessage,
    ConversationSession,
)
from app.models.user import User
from app.services import agent_service
from app.services.github_qa import QAServiceError


PREFIX = "qastream_"
_CREATED_USERS: list[str] = []

pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def env():
    db = SessionLocal()
    user = PREFIX + uuid.uuid4().hex[:8]
    db.add(User(username=user, password_hash=hash_password("Pw123456"),
                display_name="流回归", role="user", is_active=True))
    db.commit()
    conv = ConversationSession(user_id=user, title=None)
    db.add(conv)
    db.commit()
    _CREATED_USERS.append(user)
    yield db, user, str(conv.id)
    db.close()


def teardown_module(module):  # noqa: ARG001
    db = SessionLocal()
    try:
        for name in _CREATED_USERS:
            sids = db.scalars(select(ConversationSession.id).where(
                ConversationSession.user_id == name)).all()
            if sids:
                db.execute(delete(ConversationMessage).where(
                    ConversationMessage.session_id.in_(sids)))
                db.execute(delete(ConversationAgentRun).where(
                    ConversationAgentRun.session_id.in_(sids)))
                db.execute(delete(ConversationSession).where(
                    ConversationSession.id.in_(sids)))
            u = db.get(User, name)
            if u:
                db.delete(u)
        db.commit()
    finally:
        db.close()


def _parse_events(raw_chunks: list[str]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = None
    for chunk in raw_chunks:
        for line in chunk.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: "):].strip()
            elif line.startswith("data: ") and event_name:
                events.append((event_name, json.loads(line[len("data: "):])))
                event_name = None
    return events


async def _collect(stream) -> list[str]:
    return [chunk async for chunk in stream]


class _FakeStreamResp:
    def __init__(self, lines: list[str]):
        self._lines = lines
        self.status_code = 200

    def raise_for_status(self):
        return None

    async def aread(self):
        return b""

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCtx:
    def __init__(self, resp: _FakeStreamResp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    """按 OpenAI SSE 形状回放固定分片答案的模型网关替身。"""

    def __init__(self, answer_chunks: list[str], finish: str = "stop", **_kw):
        self._answer_chunks = answer_chunks
        self._finish = finish

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, _method, _url, headers=None, json=None):  # noqa: A002
        lines = [
            "data: " + json_dumps({"choices": [{"index": 0, "delta": {"content": c}}]})
            for c in self._answer_chunks
        ]
        lines.append(
            "data: " + json_dumps(
                {"choices": [{"index": 0, "delta": {}, "finish_reason": self._finish}]}))
        lines.append("data: [DONE]")
        return _FakeStreamCtx(_FakeStreamResp(lines))

    async def post(self, _url, headers=None, json=None):  # noqa: A002
        class _R:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self_inner):
                return {"choices": [{"index": 0, "message": {
                    "content": "".join(self._answer_chunks)}}]}
        return _R()


def json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _result(i: int, section: str = "industry") -> dict:
    return {
        "record_id": f"rec-{i}",
        "document_id": f"doc-{i}",
        "chunk_id": f"chunk-{i}",
        "title": f"钠离子电池测试记录{i}",
        "date": "2026-02-01",
        "source": "行业周报",
        "url": f"https://example.com/{i}",
        "body_snippet": "行业周报称钠离子电池能量密度显著提升，成本下降。",
        "score": 0.88,
        "primary_section": section,
        "chunk_metadata": {"page_numbers": [1]},
    }


def _patch_model(monkeypatch, answer: str = "钠离子电池能量密度提升[1]，成本下降[2]。"):
    monkeypatch.setattr(agent_service, "AI_API_KEY", "test-key")
    monkeypatch.setattr(agent_service, "resolve_model", lambda m=None: m or "test-model")
    monkeypatch.setattr(
        agent_service.httpx, "AsyncClient",
        lambda **kw: _FakeClient([answer[i:i + 6] for i in range(0, len(answer), 6)]))


def _patch_retrieval(monkeypatch, payload: dict):
    async def _fake(query, top_k=25, exclude_ids=None):
        return payload
    monkeypatch.setattr(agent_service, "search_canonical_raw", _fake)


def _patch_chain_off(monkeypatch):
    monkeypatch.setattr(agent_service, "_QA_CHAIN_AVAILABLE", False)


async def test_stream_with_evidence_completes_and_persists(env, monkeypatch):
    db, user, session_id = env
    _patch_model(monkeypatch)
    _patch_chain_off(monkeypatch)
    _patch_retrieval(monkeypatch, {
        "results": [_result(1), _result(2)],
        "is_relevant": True,
        "evidence": {"status": "sufficient", "count": 2},
        "retrieval_trace": {"source_route_matrix": {"industry": {"vector": {"executed": True}}}},
    })

    chunks = await _collect(agent_service.stream_agent_response(
        "钠离子电池最新进展如何？", session_id, db, current_user=user))
    events = _parse_events(chunks)
    names = [e for e, _ in events]
    stages = [p.get("stage") for e, p in events if e == "status"]

    # 主路径完整：检索 → 分析 → 生成 → done（历史 NameError 在 analyzing 前中断）
    assert "retrieving" in stages
    assert "analyzing" in stages
    assert "generating" in stages
    assert names[-1] == "done"
    assert not any(e == "error" for e in names)

    done = dict(events)[-1] if False else next(p for e, p in events if e == "done")
    assert "钠离子电池" in done["response"]
    assert done["citations"], "done 事件应携带引用"
    assert done["retrieval_summary"]["evidence"]["status"] == "sufficient"

    # 落库一致：assistant 消息 + run completed（非 running）
    db2 = SessionLocal()
    try:
        msgs = db2.scalars(select(ConversationMessage).where(
            ConversationMessage.session_id == uuid.UUID(session_id),
            ConversationMessage.role == "assistant")).all()
        assert len(msgs) == 1
        assert "钠离子电池" in msgs[0].content
        assert msgs[0].citations_json, "落库引用不应为空"
        run = db2.scalars(select(ConversationAgentRun).where(
            ConversationAgentRun.session_id == uuid.UUID(session_id))).all()[-1]
        assert run.status == "completed"
        assert run.response and "钠离子电池" in run.response
        assert run.retrieval_summary.get("evidence", {}).get("status") == "sufficient"
    finally:
        db2.close()


async def test_stream_without_evidence_abstains(env, monkeypatch):
    db, user, session_id = env
    _patch_model(monkeypatch)
    _patch_chain_off(monkeypatch)
    _patch_retrieval(monkeypatch, {
        "results": [], "is_relevant": False,
        "evidence": {"status": "insufficient", "count": 0},
    })

    chunks = await _collect(agent_service.stream_agent_response(
        "完全不相关的问题", session_id, db, current_user=user))
    events = _parse_events(chunks)
    names = [e for e, _ in events]

    done = next(p for e, p in events if e == "done")
    assert "没有足够的情报" in done["response"]
    assert done["citations"] == []
    assert not any(e == "error" for e in names)

    db2 = SessionLocal()
    try:
        run = db2.scalars(select(ConversationAgentRun).where(
            ConversationAgentRun.session_id == uuid.UUID(session_id))).all()[-1]
        assert run.status == "completed"
    finally:
        db2.close()


async def test_stream_retrieval_error_fails_run_consistently(env, monkeypatch):
    db, user, session_id = env
    _patch_model(monkeypatch)

    async def _boom(query, top_k=25, exclude_ids=None):
        raise QAServiceError("qa_upstream_unavailable", "检索服务暂不可用")
    monkeypatch.setattr(agent_service, "search_canonical_raw", _boom)

    chunks = await _collect(agent_service.stream_agent_response(
        "任意问题", session_id, db, current_user=user))
    events = _parse_events(chunks)
    err = next(p for e, p in events if e == "error")
    assert err["code"] == "qa_upstream_unavailable"
    assert err.get("retryable") is True

    db2 = SessionLocal()
    try:
        run = db2.scalars(select(ConversationAgentRun).where(
            ConversationAgentRun.session_id == uuid.UUID(session_id))).all()[-1]
        assert run.status == "failed"
        assert run.error == "qa_upstream_unavailable"
        assistants = db2.scalars(select(ConversationMessage).where(
            ConversationMessage.session_id == uuid.UUID(session_id),
            ConversationMessage.role == "assistant")).all()
        assert assistants == []
    finally:
        db2.close()


async def test_stream_verification_failure_degrades_but_completes(env, monkeypatch):
    db, user, session_id = env
    _patch_model(monkeypatch)
    _patch_retrieval(monkeypatch, {
        "results": [_result(1), _result(2)],
        "is_relevant": True,
        "evidence": {"status": "sufficient", "count": 2},
    })

    async def _failed_verification(*args, **kwargs):
        return {
            "version": "test", "refusal": False, "refusal_reason": "",
            "verification": {"status": "VERIFY_FAILED", "issues": ["数值与证据矛盾"],
                             "failure_reason": ""},
            "claim_map": {"claims": []},
            "numeric": {"checked": 2, "downgraded": 1, "worst": "CONTRADICTION"},
            "grounding": None, "independence": {}, "coverage_gate": None,
            "repair": None, "answer_status": "VERIFY_FAILED", "stop_reason": "verified_failed",
            "unsupported_major_claims": [], "boundary_message": "",
            "safety_hits": [],
        }

    monkeypatch.setattr(agent_service, "_QA_CHAIN_AVAILABLE", True)
    monkeypatch.setattr(agent_service, "_qa_chain_flags",
                        lambda: {"ANSWER_STATUS_ENABLED": True, "ANSWER_REPAIR_ENABLED": False,
                                 "EPISTEMIC_ENABLED": False})
    monkeypatch.setattr(agent_service, "run_answer_verification", _failed_verification)

    chunks = await _collect(agent_service.stream_agent_response(
        "钠离子电池成本如何？", session_id, db, current_user=user))
    events = _parse_events(chunks)
    names = [e for e, _ in events]

    # 核验失败是状态降级，不是流中断：答案仍下发、run 仍 completed
    assert names[-1] == "done"
    done = next(p for e, p in events if e == "done")
    assert done["answer_status"] == "VERIFY_FAILED"

    db2 = SessionLocal()
    try:
        run = db2.scalars(select(ConversationAgentRun).where(
            ConversationAgentRun.session_id == uuid.UUID(session_id))).all()[-1]
        assert run.status == "completed"
    finally:
        db2.close()


async def test_stream_internal_exception_finalizes_run_not_stuck(env, monkeypatch):
    """NameError 同类：实现体任何未捕获异常 → error 事件 + run=failed（2.1）。"""
    db, user, session_id = env
    _patch_model(monkeypatch)
    _patch_retrieval(monkeypatch, {
        "results": [_result(1)], "is_relevant": True,
        "evidence": {"status": "sufficient", "count": 1},
    })

    def _raising_summary(*args, **kwargs):
        raise RuntimeError("boom-before-generation")

    monkeypatch.setattr(agent_service, "_retrieval_summary", _raising_summary)

    chunks = await _collect(agent_service.stream_agent_response(
        "钠离子电池进展", session_id, db, current_user=user))
    events = _parse_events(chunks)
    err = next(p for e, p in events if e == "error")
    assert err["code"] == "internal_error"
    assert err.get("retryable") is True

    db2 = SessionLocal()
    try:
        run = db2.scalars(select(ConversationAgentRun).where(
            ConversationAgentRun.session_id == uuid.UUID(session_id))).all()[-1]
        assert run.status == "failed", "run 不得停留在 running"
        assert run.error == "RuntimeError"
        assistants = db2.scalars(select(ConversationMessage).where(
            ConversationMessage.session_id == uuid.UUID(session_id),
            ConversationMessage.role == "assistant")).all()
        assert assistants == []
    finally:
        db2.close()


async def test_stream_missing_evidence_key_is_unknown_not_crash(env, monkeypatch):
    """旧检索服务兼容：raw_payload 无 evidence 键 → unknown，不伪造、不崩溃。"""
    db, user, session_id = env
    _patch_model(monkeypatch)
    _patch_chain_off(monkeypatch)
    _patch_retrieval(monkeypatch, {"results": [_result(1)], "is_relevant": True})

    chunks = await _collect(agent_service.stream_agent_response(
        "钠离子电池进展", session_id, db, current_user=user))
    events = _parse_events(chunks)
    names = [e for e, _ in events]
    assert names[-1] == "done"
    done = next(p for e, p in events if e == "done")
    assert done["retrieval_summary"]["evidence"] == {}
    db2 = SessionLocal()
    try:
        run = db2.scalars(select(ConversationAgentRun).where(
            ConversationAgentRun.session_id == uuid.UUID(session_id))).all()[-1]
        assert run.status == "completed"
    finally:
        db2.close()

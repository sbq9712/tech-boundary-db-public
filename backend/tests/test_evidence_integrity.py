"""Regressions for cross-source budgets, version health and deletion isolation."""
from types import SimpleNamespace

import pytest
from app.services import agent_service as agent
from app.services.evidence_budget import budget_citations, fair_budgets
from app.services.index_status import _verified_document_routes, _apply_verified_states
from app.services.breadth_index_queue import _mask_key_shas_for, canonical_record_key_sha


def test_short_sources_keep_space_when_industry_is_long():
    citations = agent._normalize_citations([
        {"id": i + 1, "document_id": str(i), "title": section, "primary_section": section,
         "chunk_text": section + "证据" * 20000}
        for i, section in enumerate(("industry", "atsc", "breadth"))])
    selected, truncated = budget_citations(citations, 3000, agent.SECTION_LABELS,
                                           agent.SECTION_ORDER, agent._citation_block)
    assert truncated
    assert {c["primary_section"] for c in selected} == {"industry", "atsc", "breadth"}
    assert all(len(c["chunk_text"]) > 800 for c in selected)
    assert sum(len(agent._citation_block(c)[0]) for c in selected) < 3000
    assert fair_budgets([10, 1000, 1000], 100) == [10, 45, 45]


def test_same_title_independent_documents_are_not_merged():
    citations = [{"document_id": s, "primary_section": s, "title": "同名", "url": ""}
                 for s in ("industry", "atsc", "breadth")]
    assert len(agent._merge_citations(citations, [])) == 3


def healthy(**kwargs):
    return dict(chunks=2, live_chunks=2, content_shas=["current"], content_sha_rows=2,
                primary_sections=["industry"], vector_ok=True, bm25_ok=True,
                graph_ok=True, **kwargs)


@pytest.mark.parametrize("field,value,state", [
    ("content_shas", ["old"], "failed"),
    ("content_shas", [], "unknown"),
    ("content_sha_rows", 1, "unknown"),
    ("primary_sections", ["breadth"], "failed"),
    ("primary_sections", ["industry", "atsc"], "failed"),
    ("live_chunks", 1, "failed"),
])
def test_identity_mismatch_cannot_be_green(field, value, state):
    doc = healthy(); doc[field] = value
    result = _verified_document_routes(doc, "current", "industry", row_mode=True)
    assert {s["state"] for s in result.values()} == {state}


def test_graph_failure_is_independent_from_vector_and_keyword():
    doc = healthy(); doc["graph_ok"] = False
    result = _verified_document_routes(doc, "current", "industry", row_mode=True)
    assert result["vector"]["state"] == result["keyword"]["state"] == "complete"
    assert result["graph"]["state"] == "failed"


def test_pending_missing_document_is_queued():
    result = {"queue": {"pending": 1}, "states": {}, "status": "index_queued"}
    _apply_verified_states(result, {}, {"doc": ("current", "industry")}, row_mode=True)
    assert result["searchable"] is False
    assert {s["state"] for s in result["states"].values()} == {"queued"}


def test_industry_delete_does_not_include_legacy_breadth_identity():
    row = SimpleNamespace(title="同名", document_date="2026-10-08", url="", origin_section="industry")
    hashes = _mask_key_shas_for(row, "industry")
    assert hashes == [canonical_record_key_sha(row.title, row.document_date, "", "industry")]
    assert canonical_record_key_sha(row.title, row.document_date, "") not in hashes


def test_persisted_run_requires_own_session_and_run():
    from app.routers.conversations import get_agent_run
    from app.models.conversation import ConversationSession, ConversationAgentRun
    from fastapi import HTTPException
    from datetime import datetime, timezone
    import uuid
    sid, rid = uuid.uuid4(), uuid.uuid4()
    session = SimpleNamespace(user_id="alice")
    run = SimpleNamespace(id=rid, session_id=sid, user_id="alice", status="completed",
        query="question", response="answer", retrieval_summary={"answer_chain": {"version": "1"}},
        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc))
    db = SimpleNamespace(get=lambda model, key: session if model is ConversationSession else run)
    assert get_agent_run(sid, rid, db, "alice")["response"] == "answer"
    with pytest.raises(HTTPException) as exc:
        get_agent_run(sid, rid, db, "bob")
    assert exc.value.status_code == 404
    run.session_id = uuid.uuid4()
    with pytest.raises(HTTPException):
        get_agent_run(sid, rid, db, "alice")


def test_route_paths_survive_portal_citation_normalization():
    citation = {"id": 1, "document_id": "a", "primary_section": "atsc", "title": "report",
                "retrieval_routes": ["graph", "keyword"], "graph_paths": [{"from": "A", "to": "B", "relation": "研究"}]}
    normalized = agent._normalize_citations([citation])[0]
    assert normalized["graph_paths"] == citation["graph_paths"]
    assert normalized["retrieval_routes"] == citation["retrieval_routes"]

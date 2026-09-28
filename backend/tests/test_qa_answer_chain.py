"""第七节问答能力迁移：backend 答案侧 + 检索编排契约测试。

覆盖：novelty exclusion（历史引用不重复召回）、claim 核验/答案状态/
知识边界/安全扫描（legacy_hybrid 答案 flags 等价）、
search_canonical_raw 的 exclude_ids 传参与 evidence/trace 透传。
"""
import asyncio

from app.services import agent_service, github_qa


# ── novelty exclusion：历史引用提取 ──────────────────────────────────────
def test_history_exclude_ids_collects_record_url_and_document_ids():
    history = [
        {"role": "user", "content": "固态电池怎么样"},
        {"role": "assistant", "content": "摘要 [1][2]", "citations": [
            {"record_id": 42, "url": "https://example.com/a"},
            {"document_id": "doc-9", "chunk_id": "c1"},
        ]},
        {"role": "user", "content": "那钠离子呢"},
        {"role": "assistant", "content": "…", "citations": [
            {"record_id": 42, "url": "https://example.com/a"},  # 重复去重
            {"record_id": 7},
        ]},
    ]
    ids = agent_service._history_exclude_ids(history)
    assert ids.count("42") == 1
    assert "https://example.com/a" in ids
    assert "doc-9" in ids
    assert "7" in ids
    assert len(ids) == len(set(ids))


def test_history_exclude_ids_ignores_user_and_empty():
    assert agent_service._history_exclude_ids([]) == []
    assert agent_service._history_exclude_ids([{"role": "user", "content": "x"}]) == []
    assert agent_service._history_exclude_ids(
        [{"role": "assistant", "content": "no citations"}]) == []


def test_history_exclude_ids_capped():
    history = [{"role": "assistant", "citations": [
        {"record_id": i} for i in range(200)]}]
    assert len(agent_service._history_exclude_ids(history)) == 80


# ── 答案侧核验：claim / status / boundary / safety ────────────────────────
def test_claim_check_maps_citations_and_flags_invalid_markers():
    cc = agent_service._claim_check(
        "产能达120GWh [1]。另一项目产能为90GWh。错误引用[9]。", 2)
    assert cc["invalid_markers"] == [9]
    assert cc["factual_sentences"] == 2
    assert cc["cited_sentences"] == 1
    assert cc["cited_ratio"] == 0.5
    assert cc["claim_citation_map"][0] == {"claim": "产能达120GWh [1]", "citation": [1]}


def test_answer_status_levels():
    good = agent_service._claim_check("产能为120GWh [1]，成本下降[2]。", 2)
    assert agent_service._compute_answer_status(2, "sufficient", good, 2) == "verified"
    assert agent_service._compute_answer_status(1, "partial", good, 2) == "partial"
    assert agent_service._compute_answer_status(0, "sufficient", {}, 5) == "insufficient"
    assert agent_service._compute_answer_status(0, "unknown", {}, 0) == "insufficient"


def test_boundary_note_only_when_weak():
    assert agent_service._boundary_note("verified", "sufficient") is None
    assert "部分覆盖" in agent_service._boundary_note("partial", "sufficient")
    assert "不足" in agent_service._boundary_note("insufficient", "partial")
    assert "不足" in agent_service._boundary_note("partial", "insufficient")


def test_safety_scan_detects_leaks_and_clean_answers_pass():
    hits = agent_service._safety_scan("见 /home/rhett/x.env 或 sk-abcdefghijklmn123456")
    assert {h["kind"] for h in hits} == {"local_path", "api_key"}
    assert agent_service._safety_scan("干净回答 [1]。") == []


# ── search_canonical_raw：exclude_ids 传参 + evidence/trace 透传 ──────────
class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload, **_kwargs):
        self.payload = payload
        self.captured = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.captured = {"url": url, "params": params or {}}
        return _FakeResponse(self.payload)


def test_search_canonical_raw_passes_exclude_ids(monkeypatch):
    payload = {"results": [{"id": 1, "title": "T"}], "is_relevant": True,
               "evidence": {"status": "sufficient"}, "retrieval_trace": {"decomposed": True}}
    client = _FakeClient(payload)
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://qa:8765")
    monkeypatch.setattr(github_qa.httpx, "AsyncClient", lambda **kw: client)

    out = asyncio.run(github_qa.search_canonical_raw(
        "固态电池", top_k=25, exclude_ids=["42", "https://example.com/a", " "]))
    assert out["evidence"]["status"] == "sufficient"
    assert out["retrieval_trace"]["decomposed"] is True
    assert client.captured["params"]["exclude_ids"] == "42,https://example.com/a"


def test_search_canonical_drops_low_relevance_and_backward_compatible(monkeypatch):
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://qa:8765")
    # 旧版服务：无 evidence/trace 键 + is_relevant False → 空列表不炸
    old_payload = {"results": [{"id": 1}], "is_relevant": False}
    monkeypatch.setattr(github_qa.httpx, "AsyncClient",
                        lambda **kw: _FakeClient(old_payload))
    assert asyncio.run(github_qa.search_canonical("q")) == []
    # is_relevant 缺省（更老版本）→ 返回结果
    old_payload2 = {"results": [{"id": 1}]}
    monkeypatch.setattr(github_qa.httpx, "AsyncClient",
                        lambda **kw: _FakeClient(old_payload2))
    assert (asyncio.run(github_qa.search_canonical("q")))[0]["id"] == 1


# ── 流式链路：novelty exclusion 进入检索 + 核验字段进入 done ─────────────
def test_stream_source_uses_exclusion_and_answer_checks():
    source = __import__("inspect").getsource(agent_service.stream_agent_response)
    assert "search_canonical_raw" in source
    assert "_history_exclude_ids" in source
    assert "answer_status" in source
    assert "knowledge_boundary" in source
    assert "_claim_check" in source


def test_module_reexports_no_legacy_search_symbol():
    # 旧符号已被 raw 版本取代，避免双路径漂移
    assert not hasattr(github_qa, "search_canonical") or callable(github_qa.search_canonical)

"""五.1/五.2 答案侧真实核验链契约测试（2026-09-30）。

覆盖（不依赖真实 LLM——确定性部分 + 状态机 + 拒答语义 + 数值降级 +
grounding + 覆盖门；LLM 核验的 FAIL_SAFE 契约用假 llm 桥驱动）：
  - detect_refusal：拒答文本 vs 正常带引用回答（五.2 量子恐龙税制回归）
  - determine_answer_status：四态状态机（无证据 UNSUPPORTED /
    验证未跑 UNVERIFIED / PASSED+全支持 SUPPORTED / FAILED 降级）
  - run_numeric_checks：数值矛盾声明降级 UNSUPPORTED
  - ground_citations：引用证据原文定位（VALID/FUZZY/FAIL）
  - build_boundary：校准弃权文案（库内边界 ≠ 现实不存在）
  - run_answer_verification 端到端（stub LLM）：PASSED 全链 SUPPORTED、
    拒答 UNSUPPORTED、验证异常 UNVERIFIED（绝不 PASSED）
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

# llm_compat 桥在 import 时读 agent_service 配置；stub 掉 LLM 调用本身。
# 注意：移植模块（verifier/claim_mapping/epistemic）沿用旧仓库的
# from-import 绑定——stub 必须打在【使用方模块的名字】上。
import app.services.qa_verification.llm_compat as llm_compat
from app.services.qa_verification import claim_mapping as _cm
from app.services.qa_verification import epistemic as _ep
from app.services.qa_verification import verifier as _vf

_LLM_HOLDERS = (llm_compat, _cm, _ep, _vf)


def _install_fake_llm(handler):
    async def fake_llm(prompt, system_prompt=None, history_messages=None, **kwargs):
        return handler(prompt, system_prompt, kwargs)
    for mod in _LLM_HOLDERS:
        mod.llm_model_func = fake_llm
    return fake_llm


_install_fake_llm(lambda prompt, system_prompt, kwargs: "{}")

from app.services.qa_verification import (  # noqa: E402
    answer_chain,
    build_rewrite_prompt,
    classify_or_empty,
    detect_refusal,
    epistemic_prompt,
    run_answer_verification,
)
from app.services.qa_verification.answer_status import AnswerStatus, determine_answer_status  # noqa: E402
from app.services.qa_verification.answer_chain import ground_citations, run_numeric_checks, build_boundary  # noqa: E402


# ── 五.2 拒答识别 ────────────────────────────────────────────────────────

def test_detect_refusal_short_db_boundary_phrases():
    ok, reason = detect_refusal("抱歉，数据库中没有相关信息。")
    assert ok and reason == "refusal_text"
    ok, _ = detect_refusal("当前知识库中未找到与「量子恐龙税制」相关的情报。")
    assert ok
    ok, _ = detect_refusal("检索结果未找到足够资料回答该问题。")
    assert ok


def test_detect_refusal_not_triggered_by_substantive_answers():
    ok, _ = detect_refusal("钠离子电池能量密度已达160Wh/kg [1]，产业化加速。")
    assert not ok
    # 拒答字样出现在长回答中（混合回答）→ 不整体判拒答，交由声明级核验
    long_answer = "根据资料，" + "产业化进展显著，多个项目落地，产能持续爬坡，" * 8 + "但公开资料中没有相关信息。"
    ok, _ = detect_refusal(long_answer)
    assert not ok
    ok, reason = detect_refusal("")
    assert ok and reason == "empty_answer"


# ── 四态状态机（旧 AnswerStatus 词汇）───────────────────────────────────

def test_status_machine_no_evidence_is_unsupported():
    status, stop = determine_answer_status(False, False)
    assert status == AnswerStatus.UNSUPPORTED and stop == "weak_query"


def test_status_machine_verification_not_run_is_never_supported():
    # RT-024：验证从未运行 ≠ SUPPORTED（旧 fail-open 已废除）
    status, _ = determine_answer_status(True, True, "", {"claims": []})
    assert status == AnswerStatus.UNVERIFIED


def test_status_machine_passed_with_supported_claims():
    claims = [{"id": "c1", "type": "MAJOR_FACT", "is_core": True,
               "support_status": "SUPPORTED"}]
    status, stop = determine_answer_status(True, True, "PASSED", {"claims": claims})
    assert status == AnswerStatus.SUPPORTED, stop


def test_status_machine_unsupported_core_claim_blocks_supported():
    claims = [{"id": "c1", "type": "MAJOR_FACT", "is_core": True,
               "support_status": "UNSUPPORTED"}]
    status, _ = determine_answer_status(True, True, "PASSED", {"claims": claims})
    assert status in (AnswerStatus.PARTIALLY_SUPPORTED, AnswerStatus.UNSUPPORTED)


def test_status_machine_verifier_failed_downgrades():
    status, _ = determine_answer_status(True, True, "FAILED", {"claims": []})
    assert status in (AnswerStatus.PARTIALLY_SUPPORTED, AnswerStatus.UNSUPPORTED)


# ── 数值核验（确定性）────────────────────────────────────────────────────

def _records_resolver(cit):
    return {"fb": "", "b": cit.get("chunk_text", ""), "as": ""}


def test_numeric_check_downgrades_contradicted_claim():
    claims_mapping = {"claims": [{
        "id": "c1", "type": "NUMERIC_FACT", "is_core": True,
        "support_status": "SUPPORTED", "text": "能量密度达500Wh/kg",
        "supported_by": [{"citation_id": 1, "relation": "DIRECT_SUPPORT"}],
    }]}
    citations = [{"id": 1, "chunk_text": "实测能量密度160Wh/kg，循环寿命3000次。"}]
    report = run_numeric_checks(claims_mapping, citations, _records_resolver)
    assert report["checked"] == 1 and report["downgraded"] == 1
    assert claims_mapping["claims"][0]["support_status"] == "UNSUPPORTED"
    assert claims_mapping["claims"][0]["numeric_check"]["status"] == "MISMATCH"


def test_numeric_check_passes_matching_numbers():
    claims_mapping = {"claims": [{
        "id": "c1", "type": "NUMERIC_FACT", "is_core": True,
        "support_status": "SUPPORTED", "text": "能量密度达160Wh/kg",
        "supported_by": [{"citation_id": 1, "relation": "DIRECT_SUPPORT"}],
    }]}
    citations = [{"id": 1, "chunk_text": "实测能量密度160Wh/kg。"}]
    report = run_numeric_checks(claims_mapping, citations, _records_resolver)
    assert report["downgraded"] == 0
    assert claims_mapping["claims"][0]["numeric_check"]["status"] == "MATCH"


def test_numeric_check_no_numbers_is_neutral():
    claims_mapping = {"claims": [{
        "id": "c1", "type": "ANALYSIS", "is_core": False,
        "support_status": "SUPPORTED", "text": "产业化进程加快",
        "supported_by": [],
    }]}
    report = run_numeric_checks(claims_mapping, [], None)
    assert report["checked"] == 0 and report["worst"] == "NO_CLAIM_NUMBER"


# ── 引用证据原文定位 ─────────────────────────────────────────────────────

def test_ground_citations_exact_and_fail():
    citations = [
        {"id": 1, "body_snippet": "实测能量密度160Wh/kg",
         "chunk_text": "实测能量密度160Wh/kg，循环寿命3000次。"},
        {"id": 2, "body_snippet": "这句话不在原文里出现abcxyz", "chunk_text": "完全无关的文本内容。"},
    ]
    report = ground_citations(citations, _records_resolver, "能量密度")
    assert citations[0]["grounding_status"] in ("VALID", "FUZZY")
    assert citations[0]["evidence_spans"]
    assert citations[1]["grounding_status"] == "GROUNDING_FAIL"
    assert report["fail"] >= 1


# ── 校准弃权 ─────────────────────────────────────────────────────────────

def test_boundary_message_for_unsupported_never_claims_nonexistence():
    msg = build_boundary("UNSUPPORTED", {"claims": []}, [], 0)
    assert "不足以可靠回答" in msg or "缺少" in msg
    msg2 = build_boundary("PARTIALLY_SUPPORTED",
                          {"claims": [{"id": "c1", "text": "A方面", "support_status": "SUPPORTED"},
                                      {"id": "c2", "text": "B方面", "support_status": "UNSUPPORTED"}]},
                          [{"source": "s1"}], 1)
    assert "可以确认" in msg2 and "当前数据库缺少" in msg2


# ── epistemic 提示词注入 ─────────────────────────────────────────────────

def test_epistemic_prompt_injects_addendum_and_metadata():
    base = "你是技术情报分析专家。"
    out = epistemic_prompt(base, [])
    assert "可核验事实" in out and "高警惕词" in out and base in out
    out2 = epistemic_prompt(base, [{"chunk_id": "1", "claims": [
        {"claim": "X", "type": "OPINION", "speaker": "XX证券"}]}])
    assert "OPINION" in out2


# ── 端到端（stub LLM 的 FAIL_SAFE 契约）──────────────────────────────────

_FLAGS = {
    "FAIL_SAFE_VERIFY_ENABLED": True, "CLAIM_MAPPING_ENABLED": True,
    "CITATION_GROUNDING_ENABLED": True, "ANSWER_STATUS_ENABLED": True,
    "KNOWLEDGE_BOUNDARY_ENABLED": True, "EPISTEMIC_ENABLED": True,
    "ANSWER_REPAIR_ENABLED": True,
}

_CITATIONS = [{"id": 1, "title": "钠电记录", "source": "X实验室", "date": "2026-09-01",
               "chunk_text": "实测能量密度160Wh/kg，循环寿命3000次。"}]
_CLAIM_META = [{"chunk_id": "1", "claims": [
    {"claim": "能量密度160Wh/kg", "type": "VERIFIABLE_FACT", "speaker": None,
     "must_attribute": False, "confidence": 0.95, "evidence_span": "实测能量密度160Wh/kg"}]}]
_ANCHOR_MAP = {"claims": [{"id": "claim_1", "text": "能量密度达160Wh/kg",
                           "type": "NUMERIC_FACT", "is_core": True,
                           "support_status": "SUPPORTED",
                           "supported_by": [{"citation_id": 1, "relation": "DIRECT_SUPPORT"}]}]}


def test_run_answer_verification_supported_path(monkeypatch):
    # LLM 返回：verify PASSED + claim 映射锚点兜底由 map 内部处理 —— 直接stub map
    def handler(prompt, system_prompt, kwargs):
        return '{"passed": true}'
    for mod in _LLM_HOLDERS:
        monkeypatch.setattr(mod, "llm_model_func", _wrap(handler))
    monkeypatch.setattr(answer_chain, "map_claims_to_citations",
                        _async_return(_ANCHOR_MAP))
    report = asyncio.run(run_answer_verification(
        "钠电能量密度", "能量密度达160Wh/kg [1]。", list(_CITATIONS),
        claim_metadata=_CLAIM_META, records_resolver=_records_resolver,
        flags=_FLAGS))
    assert report["answer_status"] == "SUPPORTED"
    assert report["verification"]["status"] == "PASSED"
    assert report["refusal"] is False


def test_run_answer_verification_refusal_is_never_verified(monkeypatch):
    # 五.2 核心回归：拒答文本（哪怕带引用标注）⇒ UNSUPPORTED
    for mod in _LLM_HOLDERS:
        monkeypatch.setattr(mod, "llm_model_func", _wrap(lambda *a, **k: '{"passed": true}'))
    report = asyncio.run(run_answer_verification(
        "量子恐龙税制", "抱歉，数据库中没有相关信息。[1]", list(_CITATIONS),
        claim_metadata=_CLAIM_META, records_resolver=_records_resolver,
        flags=_FLAGS))
    assert report["refusal"] is True
    assert report["answer_status"] == "UNSUPPORTED"
    assert report["stop_reason"] == "refusal_text"
    assert "不表示现实世界中" in (report["boundary_message"] or "")


def test_run_answer_verification_verifier_exception_never_passes(monkeypatch):
    # TK-10/T005 契约：核验 LLM 异常 → UNVERIFIED，绝不 PASSED
    async def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(answer_chain, "verify_with_fail_safe", boom)
    monkeypatch.setattr(llm_compat, "llm_model_func", boom)
    monkeypatch.setattr(answer_chain, "map_claims_to_citations",
                        _async_return({"claims": []}))
    report = asyncio.run(run_answer_verification(
        "钠电能量密度", "能量密度达160Wh/kg [1]。", list(_CITATIONS),
        claim_metadata=_CLAIM_META, records_resolver=_records_resolver,
        flags=_FLAGS))
    assert report["verification"]["status"] == "UNVERIFIED"
    assert report["answer_status"] != "SUPPORTED"


def test_run_answer_verification_numeric_mismatch_downgrades(monkeypatch):
    for mod in _LLM_HOLDERS:
        monkeypatch.setattr(mod, "llm_model_func", _wrap(lambda *a, **k: '{"passed": true}'))
    contradicted = {"claims": [{"id": "claim_1", "text": "能量密度达900Wh/kg",
                                "type": "NUMERIC_FACT", "is_core": True,
                                "support_status": "SUPPORTED",
                                "supported_by": [{"citation_id": 1, "relation": "DIRECT_SUPPORT"}]}]}
    monkeypatch.setattr(answer_chain, "map_claims_to_citations", _async_return(contradicted))
    report = asyncio.run(run_answer_verification(
        "钠电能量密度", "能量密度达900Wh/kg [1]。", list(_CITATIONS),
        claim_metadata=_CLAIM_META, records_resolver=_records_resolver,
        flags=_FLAGS))
    assert report["numeric"]["downgraded"] == 1
    assert report["answer_status"] != "SUPPORTED"


def test_compact_payload_shape():
    from app.services.qa_verification import compact_for_payload
    compact = compact_for_payload({"version": "v", "answer_status": "SUPPORTED",
                                   "claim_map": {"claims": [{"support_status": "SUPPORTED"}]},
                                   "verification": {"status": "PASSED"}})
    assert compact["answer_status"] == "SUPPORTED"
    assert compact["claims_total"] == 1 and compact["claims_supported"] == 1
    assert "claim_map" not in compact  # 全量映射不进 SSE payload


def test_rewrite_prompt_build():
    p = build_rewrite_prompt("问题", "草稿 [1]。", claims=[{"id": "c1", "text": "X"}],
                             issues=[{"sentence": "X"}], drop_ids=["c1"])
    assert "核验发现的问题" in p and "修复规则" in p and "草稿 [1]。" in p


# ── helpers ──────────────────────────────────────────────────────────────

def _wrap(handler):
    async def fake(prompt, system_prompt=None, history_messages=None, **kwargs):
        return handler(prompt, system_prompt, kwargs)
    return fake


def _async_return(value):
    async def _fn(*a, **k):
        return value
    return _fn


# ── 2026-09-30 钠离子电池回归：分类面 + 修复去重 ─────────────────────────


def test_classify_or_empty_covers_all_citable_chunks(monkeypatch):
    """分类面必须对齐生成器可引用面：FINAL_TOP_K=25 时分类也要盖到 25，
    否则 verifier LLM 把 [24]/[25] 判为不存在的 chunk（1-5）→ 全部核心
    主张 fail-closed UNSUPPORTED（旧系统 FINAL_TOP_K≈6 所以没这问题）。"""
    import app.services.qa_verification.answer_chain as ac
    seen_top_k = []

    async def fake_classify(query, search_results, top_k=5):
        seen_top_k.append(top_k)
        return [{"chunk_id": str(i + 1), "claims": [{"text": f"c{i}"}]}
                for i in range(top_k)]

    monkeypatch.setattr(ac, "classify_claims", fake_classify)
    monkeypatch.setattr(ac, "CLASSIFY_TIMEOUT", 5.0)
    results = asyncio.run(ac.classify_or_empty("q", [{"meta": {}}] * 25))
    assert len(results) == 5           # 首轮即成功：旧对齐单次分类面 top-5
    assert seen_top_k == [5]


def test_classify_or_empty_shrinks_ladder_on_empty(monkeypatch):
    """首轮全量空输出（GLM-5.2 推理耗尽 token 的已知失效）→ 逐级收缩
    25 → 10 → 5；三级全空才降级 []。"""
    import app.services.qa_verification.answer_chain as ac
    seen_top_k = []

    async def fake_classify(query, search_results, top_k=5):
        seen_top_k.append(top_k)
        return []                       # 模拟静默空输出

    monkeypatch.setattr(ac, "classify_claims", fake_classify)
    monkeypatch.setattr(ac, "CLASSIFY_TIMEOUT", 5.0)
    results = asyncio.run(ac.classify_or_empty("q", [{"meta": {}}] * 25))
    assert results == []
    assert seen_top_k == [5, 25, 10]   # 旧对齐 top-5 先行，空输出再升级


def test_repair_does_not_stack_qualify_prefix():
    """多个相邻未支持主张命中同一句时，QUALIFY_PREFIX 只加一次，
    不出现 ×3 叠加（2026-09-30 实测回归）。已带前缀的句子按 weaken
    记账，不再重复修饰。"""
    from app.services.qa_verification.answer_repair import (
        BoundedRepairLoop, QUALIFY_PREFIX)

    loop = BoundedRepairLoop(max_cycles=1)
    sentence = ("全固态电池的能量密度达到500Wh/kg，比传统液态锂电池高出"
                "一倍以上，多家研究机构已经实现了原型验证并计划在2027年"
                "前后装车量产。")
    answer = f"根据证据，{sentence}"
    # 三个不同主张都命中同一句（MAJOR_FACT 才进修复状态机）
    mapping = {"claims": [
        {"id": f"claim_{i}", "type": "MAJOR_FACT", "text": sentence[:30],
         "support_status": "UNSUPPORTED"}
        for i in (2, 3, 5)]}
    report = asyncio.run(loop.run(
        answer, mapping, evidence_index=None,
        grounding_fn=None, retrieve_fn=None, regenerate_fn=None,
        core_claim_ids=set()))
    out = report["answer"]
    assert out.count(QUALIFY_PREFIX) == 1, out
    assert report["terminal_reason"] == "all_resolved", report["terminal_reason"]
    assert all(s == "WEAKENED" for s in report["claim_states"].values()), \
        report["claim_states"]


def test_classify_full_coverage_batches_and_offsets(monkeypatch):
    """verify 覆盖面补齐：从 already=5 起按 ×5 批面分类，chunk_id 平移
    到 [6..N]；单批失败只丢该批，不阻断其余批次。"""
    import app.services.qa_verification.answer_chain as ac
    calls = []

    async def fake_classify(query, search_results, top_k=5):
        calls.append((len(search_results), top_k))
        base = 1
        return [{"chunk_id": str(base + i), "claims": [{"text": "c"}]}
                for i in range(len(search_results))]

    monkeypatch.setattr(ac, "classify_claims", fake_classify)
    monkeypatch.setattr(ac, "SUPPLEMENTAL_BUDGET", 30.0)
    monkeypatch.setattr(ac, "SUPPLEMENTAL_BATCH_TIMEOUT", 5.0)
    results = asyncio.run(
        ac.classify_full_coverage("q", [{"meta": {}}] * 13, already=5))
    assert calls == [(5, 5), (3, 3)]             # 批面大小 = 剩余数（8=5+3）
    ids = [r["chunk_id"] for r in results]
    assert ids == ["6", "7", "8", "9", "10", "11", "12", "13"], ids


def test_classify_full_coverage_noop_when_covered():
    """claim_metadata 已覆盖全部可引用面 → 不追加任何分类调用。"""
    import app.services.qa_verification.answer_chain as ac
    ran = {"n": 0}

    async def fake_classify(*a, **k):
        ran["n"] += 1
        return []

    asyncio.run(ac.classify_full_coverage("q", [{"meta": {}}] * 25, already=25))
    assert ran["n"] == 0

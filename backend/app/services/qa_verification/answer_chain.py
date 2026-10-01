#!/usr/bin/env python3
"""legacy_hybrid 答案侧真实核验链（五.1/五.2，2026-09-30）。

旧系统真实实现（tech-db/qa-backend，QA_PIPELINE_PROFILE=legacy_hybrid 实跑
开关：AGENTIC..KNOWLEDGE_BOUNDARY 全 ON，EXACT_GROUNDING/TERMINAL_RENDERER
OFF）在生成前后依次执行：

  Retriever → [epistemic.classify_claims 认识论分类 top-5]
           → Generator（build_epistemic_system_prompt 注入分类元数据 +
             EPISTEMIC_SYSTEM_ADDENDUM）
           → [verifier.verify_with_fail_safe 事实核验（异常/超时/坏 JSON
             一律 UNVERIFIED，绝不 PASSED）]
           → [claim_mapping.map_claims_to_citations 声明→引用映射 +
             attach_span_lineage/claim_independence 溯源]
           → [citation_grounding.ground_citation_evidence 引用证据原文定位]
           → [numeric_facts.verify_numeric_claim 数值核验（确定性）]
           → [answer_repair.BoundedRepairLoop 有界修复（本仓库按五.1 接入）]
           → [answer_status.determine_answer_status 状态机定案]
           → [knowledge_boundary 校准弃权（库内边界 ≠ 现实不存在）]

本模块把该链封装为两侧（canonical-qa server 与 backend agent_service）共用
的编排实现；逐字移植的核验模块与本文件同目录（backend 侧为
backend/app/services/qa_verification/ 包，仅 import 行差异，逻辑逐字节同）。

五.2 状态语义：拒答（回答文本本身在说"没有相关资料"）走状态机
no_evidence → UNSUPPORTED，绝不因带引用标注就报 verified——
「量子恐龙税制被拒答却 evidence_status=sufficient/answer_status=verified」
的误报即因此前的标记计数启发式把拒答文本当成已验证事实。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Callable, Optional

from app.services.qa_verification.answer_status import AnswerStatus, determine_answer_status
from app.services.qa_verification.answer_repair import BoundedRepairLoop
from app.services.qa_verification.claim_mapping import (
    SUPPORTING_RELATIONS,
    attach_span_lineage,
    check_claim_coverage,
    claim_independence,
    get_unsupported_major_claims,
    map_claims_to_citations,
)
from app.services.qa_verification.citation_grounding import ground_citation_evidence
from app.services.qa_verification.evidence_metadata import infer_evidence_role
from app.services.qa_verification.epistemic import build_epistemic_system_prompt, classify_claims
from app.services.qa_verification.knowledge_boundary import (
    AnswerStatus as KBStatus,
    assess_coverage,
    format_boundary_message,
)
from app.services.qa_verification.numeric_facts import verify_numeric_claim
from app.services.qa_verification.verifier import (
    VERIFY_FAILED,
    VERIFY_PASSED,
    VERIFY_UNVERIFIED,
    verify_with_fail_safe,
)

ANSWER_CHAIN_VERSION = "legacy-hybrid-answer-1.0.0"

# 单个 LLM 核验步骤的墙钟上限（旧系统由 QueryBudget/BUDGET_FUSE 承担；
# 本仓库无预算熔断器，用超时 + FAIL_SAFE 降级承担同一职责）。
# 注意：verify_with_fail_safe / map_claims_to_citations 内部自带多次重试
# （verifier 内层 60s/次 × 3 次；mapping 2 组负载 × 2 次）——外层预算必须
# 覆盖内层完整重试序列，否则外层会拦腰截断（2026-09-30 实测 90s 截断
# verifier 重试 → UNVERIFIED:timeout）。
# 分类面策略（2026-09-30 钠离子电池实测回归定稿）：生成前首轮 top-5
# （旧系统单次分类面，延迟/提示词注入对齐），空输出再升级到全可引用面
# （新部署 FINAL_TOP_K=25）；25 chunk 单次调用易触发 GLM-5.2 推理耗尽
# token → content 空 → 静默 []，故 verify 侧用 ×5 批面补充分类兜底
# （见 classify_full_coverage）。verifier 内层每次 LLM 调用受 verifier.py
# 的 QA_VERIFY_TIMEOUT（缺省 60s）约束——与本文件外层预算是两个旋钮，
# 不能共用同名 env（部署置 QA_VERIFY_TIMEOUT=90 时外层不受影响）。
CLASSIFY_TIMEOUT = float(__import__("os").environ.get("QA_CLASSIFY_TIMEOUT", "120"))
VERIFY_BUDGET = float(__import__("os").environ.get("QA_VERIFY_BUDGET", "300"))
# mapping 内层 2 组负载 ×2 次 LLM（8192 token/次，GLM-5.2 单次可达
# ~140s）——外层必须覆盖完整内层序列（2026-09-30 sodium7 实测 160s
# 拦腰截断 → claim_mapping timeout → claims 空，与旧系统语义一致但
# 白耗内层预算）。
MAPPING_TIMEOUT = float(__import__("os").environ.get("QA_MAPPING_TIMEOUT", "300"))
SUPPLEMENTAL_BATCH = 5          # 旧系统 classify_claims 单次分类面
SUPPLEMENTAL_BATCH_TIMEOUT = 60.0
SUPPLEMENTAL_BUDGET = float(
    __import__("os").environ.get("QA_SUPPLEMENTAL_CLASSIFY_BUDGET", "240"))

# 数值核验的证据文本预算（与旧 verifier 的 evidence 截断同量级）
NUMERIC_EVIDENCE_CAP = 4000

# ── 五.2：拒答文本的确定性识别 ────────────────────────────────────────────
# 命中且回答很短 ⇒ 这是一条「库内无资料」的拒答，不是已验证事实。
_REFUSAL_RE = re.compile(
    r"(数据库|知识库|库中|资料|检索结果|检索到的资料|情报库)"
    r"(中|里)?(没有|未找到|找不到|未检索到|未包含|缺少)"
)
_REFUSAL_TAIL_RE = re.compile(r"(情报|信息|资料|证据|记录|内容|相关|足够|充分)")
# 真实拒答是 1-2 句（「抱歉，数据库中没有相关信息。」≈15 字）；
# 120 字以上的「长回答尾部附带缺料说明」属混合回答，交由声明级核验。
_REFUSAL_MAX_CHARS = 120


def detect_refusal(answer: str) -> tuple[bool, str]:
    """回答文本本身是拒答 ⇒ (True, reason)。短回答 + 明确库内缺料表述。

    判「短」是为了不误伤「先拒答部分角度、再基于资料回答其余」的混合回答；
    混合回答由 verify/claim-mapping 链按声明级别处理。"""
    text = (answer or "").strip()
    if not text:
        return True, "empty_answer"
    if len(text) <= _REFUSAL_MAX_CHARS and _REFUSAL_RE.search(text) \
            and _REFUSAL_TAIL_RE.search(text):
        return True, "refusal_text"
    return False, ""


# ── 生成前：认识论分类 + 提示词注入 ─────────────────────────────────────


async def classify_or_empty(query: str, search_results: list) -> list:
    """epistemic.classify_claims 的 FAIL_SAFE 包装：异常/超时 → []。

    旧系统语义：epistemic 是增强不是关键路径，预算不足/LLM 故障只降级，
    绝不阻断生成。2026-09-30 实测（GLM-5.2）：推理型输出偶发耗尽 token
    预算 → content 为空 → 解析 []（静默），验证链随之 fail-closed
    UNVERIFIED——重试并收缩分类面，重试成功即恢复完整核验链；全部
    皆空才降级。

    2026-09-30 钠离子电池实测回归：新部署 FINAL_TOP_K=25 而分类只盖
    top-5 → verifier LLM 只见到 chunk 1-5 的认识论元数据，把 [24]/[25]
    引用判为"不对应任何已有chunk（1-5）"、全部 chunk claims 为空 →
    全部核心主张 fail-closed UNSUPPORTED。旧部署 FINAL_TOP_K≈6，top-5
    分类天然全覆盖，因此老系统没有这个问题。修复：分类面必须对齐
    生成器可引用面（≤25），超时/空输出时再逐级收缩。"""
    if not search_results:
        return []
    full_k = max(1, min(len(search_results), 25))
    # 首轮 top-5：旧系统单次分类面（延迟 + 提示词注入对齐）；空输出
    # （GLM-5.2 推理耗尽 token 的已知失效）再逐级升级分类面。
    for attempt, top_k in ((1, min(full_k, 5)), (2, full_k),
                           (3, min(full_k, 10))):
        try:
            result = await asyncio.wait_for(
                classify_claims(query, search_results, top_k=top_k),
                timeout=CLASSIFY_TIMEOUT)
            if result:
                return result
            print(f"[answer-chain] classify attempt {attempt}: 空结果"
                  f"（LLM 输出为空/无法解析，top_k={top_k}）", flush=True)
        except asyncio.TimeoutError:
            print(f"[answer-chain] classify attempt {attempt} timeout"
                  f"（{CLASSIFY_TIMEOUT}s，top_k={top_k}）", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[answer-chain] classify attempt {attempt} degraded: "
                  f"{exc.__class__.__name__}: {str(exc)[:120]}", flush=True)
    return []


async def _classify_slice(query: str, slice_results: list, id_offset: int,
                          deadline: float) -> list:
    """单个分类批面（×5，旧系统单次调用大小）：FAIL_SAFE，chunk_id 平移。"""
    try:
        remaining = deadline - __import__("time").monotonic()
        if remaining <= 0:
            return []
        result = await asyncio.wait_for(
            classify_claims(query, slice_results, top_k=len(slice_results)),
            timeout=min(SUPPLEMENTAL_BATCH_TIMEOUT, remaining))
    except Exception as exc:  # noqa: BLE001
        print(f"[answer-chain] supplemental classify chunk {id_offset + 1}-"
              f"{id_offset + len(slice_results)} degraded: "
              f"{exc.__class__.__name__}: {str(exc)[:120]}", flush=True)
        return []
    for item in (result or []):
        if isinstance(item, dict):
            try:
                cid = int(str(item.get("chunk_id", "0")))
                item["chunk_id"] = str(cid + id_offset)
            except (TypeError, ValueError):
                pass
    return result or []


async def classify_full_coverage(query: str, search_results: list,
                                 already: int) -> list:
    """verify 侧补充分类：生成前只分类 top-5（旧对齐），而生成器可引用
    全部 FINAL_TOP_K=25 条——verifier 的有效 chunk 集必须覆盖全部可引用
    面，否则 [24]/[25] 引用被误判为不存在的 chunk（2026-09-30 钠离子
    电池实测回归）。批面 ×5（旧单次分类面大小）逐批分类、chunk_id 平移；
    单批失败只丢该批（FAIL_SAFE 降级，不阻断核验链）。"""
    if not search_results or already >= len(search_results):
        return []
    deadline = __import__("time").monotonic() + SUPPLEMENTAL_BUDGET
    out: list = []
    for start in range(already, len(search_results), SUPPLEMENTAL_BATCH):
        chunk = search_results[start:start + SUPPLEMENTAL_BATCH]
        out.extend(await _classify_slice(query, chunk, start, deadline))
    return out


def epistemic_prompt(base_prompt: str, claim_metadata: list) -> str:
    """基础提示词 + EPISTEMIC_SYSTEM_ADDENDUM + 分类元数据（旧 build_-
    epistemic_system_prompt 的直通包装；无分类元数据时也注入规则文本，
    与旧系统一致——addendum 不依赖元数据存在）。"""
    try:
        return build_epistemic_system_prompt(base_prompt, claim_metadata or [])
    except Exception:  # noqa: BLE001
        return base_prompt


# ── 生成后：全链核验 ─────────────────────────────────────────────────────


def _numeric_evidence_text(claim: dict, citations_by_id: dict,
                           records_resolver: Optional[Callable]) -> str:
    """该声明所引证据的原文拼接（数值核验对 full text，非截断摘要）。"""
    parts = []
    for ref in claim.get("supported_by", []) or []:
        if ref.get("relation") not in SUPPORTING_RELATIONS:
            continue
        cit = citations_by_id.get(ref.get("citation_id"))
        if not cit:
            continue
        rec = records_resolver(cit) if records_resolver else None
        text = ""
        if rec:
            text = (rec.get("fb", "") or rec.get("b", "") or rec.get("as", "") or "")
        text = text or cit.get("chunk_text", "") or cit.get("body_snippet", "") or ""
        if text:
            parts.append(text)
        if sum(len(p) for p in parts) >= NUMERIC_EVIDENCE_CAP:
            break
    return "\n".join(parts)[:NUMERIC_EVIDENCE_CAP]


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def run_numeric_checks(claims_mapping: dict, citations: list,
                       records_resolver: Optional[Callable]) -> dict:
    """数值核验（确定性，numeric_facts.verify_numeric_claim）。

    声明含数字且其支撑证据中找不到一致数字 ⇒ 该声明降级为 UNSUPPORTED
    （MISMATCH/SCOPE_MISMATCH/UNIT_FAMILY_MISMATCH；RT-022 最差者胜）。
    返回汇总：checked / downgraded / worst。"""
    citations_by_id = {c.get("id"): c for c in citations or []}
    checked = downgraded = 0
    worst = "NO_CLAIM_NUMBER"
    rank = {"MATCH": 0, "NO_CLAIM_NUMBER": 0, "NO_EVIDENCE_NUMBER": 1,
            "UNIT_FAMILY_MISMATCH": 2, "SCOPE_MISMATCH": 3, "MISMATCH": 4}
    for claim in (claims_mapping or {}).get("claims", []):
        text = claim.get("text", "") or ""
        if not _NUMBER_RE.search(text):
            continue
        report = verify_numeric_claim(
            text, _numeric_evidence_text(claim, citations_by_id, records_resolver))
        status = str(report.get("status", "NO_CLAIM_NUMBER"))
        claim["numeric_check"] = {"status": status,
                                  "checked": report.get("checked", 0),
                                  "findings": report.get("findings", [])[:5]}
        checked += 1
        if rank.get(status, 0) > rank.get(worst, 0):
            worst = status
        if status in ("MISMATCH", "SCOPE_MISMATCH", "UNIT_FAMILY_MISMATCH"):
            # 数值与证据矛盾：不得以 SUPPORTED 身份进入状态机（五.1 数值核验）
            claim["support_status"] = "UNSUPPORTED"
            claim["numeric_downgraded"] = True
            downgraded += 1
    return {"checked": checked, "downgraded": downgraded, "worst": worst}


def ground_citations(citations: list, records_resolver: Callable,
                     query: str) -> dict:
    """引用证据原文定位（T003 citation_grounding，逐字移植实现）。

    每个 citation 获得 evidence_span/start/end/grounding_status/
    source_label/evidence_spans/highlight——引用卡与溯源 UI 的锚点。"""
    valid = fuzzy = failed = 0
    for cit in citations or []:
        rec = records_resolver(cit)
        if rec is None:
            cit["grounding_status"] = "GROUNDING_FAIL"
            failed += 1
            continue
        try:
            g = ground_citation_evidence(
                rec, proposed_span=cit.get("body_snippet", "") or "",
                claim_text="", query=query)
        except Exception:  # noqa: BLE001
            g = {"grounding_status": "GROUNDING_FAIL", "evidence_span": "",
                 "start_offset": -1, "end_offset": -1, "source_field": "none",
                 "highlight": ""}
        status = g.get("grounding_status", "GROUNDING_FAIL")
        cit["grounding_status"] = status
        cit["evidence_span"] = g.get("evidence_span", "")
        cit["evidence_start"] = g.get("start_offset", -1)
        cit["evidence_end"] = g.get("end_offset", -1)
        cit["highlight"] = g.get("highlight", "")
        if g.get("source_field") == "as":
            cit["source_label"] = "AI_SUMMARY"
        else:
            cit.setdefault("source_label", "ORIGINAL")
        if status in ("VALID", "FUZZY"):
            cit["evidence_spans"] = [{"text": g.get("evidence_span", ""),
                                      "start": g.get("start_offset", -1),
                                      "end": g.get("end_offset", -1)}]
            if status == "VALID":
                valid += 1
            else:
                fuzzy += 1
        else:
            cit["evidence_spans"] = []
            failed += 1
    return {"valid": valid, "fuzzy": fuzzy, "fail": failed}


def _attach_lineage(claims_mapping: dict, citations: list,
                    records_resolver: Optional[Callable]) -> dict:
    """T048 溯源 + 独立性计数（旧 legacy 路径同款；resolver 失败静默跳过）。"""
    if records_resolver is None:
        return {}
    try:
        provenance_map = {}
        records_by_id = {}
        for cit in citations or []:
            rid = cit.get("record_id")
            if rid is None:
                continue
            rec = records_resolver(cit)
            if rec is None:
                continue
            records_by_id[rid] = rec
            records_by_id[str(rid)] = rec
            provenance_map[rid] = {
                "evidence_role": infer_evidence_role(rec),
                # legacy 路径（非 EvidencePackage）：每条记录一个独立组
                "independent_group_id": f"record:{rid}",
            }
        attach_span_lineage(claims_mapping, citations,
                            provenance_map=provenance_map,
                            records_by_id=records_by_id)
        return claim_independence(claims_mapping,
                                  provenance_map=provenance_map,
                                  records_by_id=records_by_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[answer-chain] lineage degraded: {exc.__class__.__name__}", flush=True)
        return {}


REWRITE_SYSTEM_PROMPT = "你是事实核查修复助手。只输出修正后的完整回答，不要输出任何解释。"


def build_rewrite_prompt(query: str, answer: str, claims: list | None = None,
                         issues: list | None = None,
                         drop_ids: list | None = None) -> str:
    """RT-026 修复改写提示词：只修问题句，其余逐字保留，不新增事实。"""
    claims = claims or []
    issues = issues or []
    drop_texts = [c.get("text", "") for c in claims
                  if c.get("id") in set(drop_ids or [])]
    parts = [f"用户问题：{query}", ""]
    if issues:
        parts.append("核验发现的问题（JSON）：")
        parts.append(json.dumps(issues[:8], ensure_ascii=False, indent=1)[:2000])
        parts.append("")
    if drop_texts:
        parts.append("以下陈述未获证据支持，须删除或改为明确的归属性/不确定性表述（不得作为事实保留）：")
        parts.extend(f"- {t[:120]}" for t in drop_texts[:8])
        parts.append("")
    parts.append("修复规则：")
    parts.append("1. 仅修正上述问题句；其余内容（含引用标注 [n]）逐字保留")
    parts.append("2. 不新增任何事实、数字或来源")
    parts.append("3. 修正方式：降低确定性（加「有观点认为/据报道/预计」）、恢复归属（「XX机构称」）、或直接删除该句")
    parts.append("4. 全部问题句都处理后再输出完整回答")
    parts.append("")
    parts.append("回答草稿：")
    parts.append(answer)
    return "\n".join(parts)


async def _repair_if_failed(query: str, answer: str, claims_mapping: dict,
                            citations: list, records_resolver: Optional[Callable],
                            llm_rewrite: Optional[Callable],
                            issues: Optional[list] = None) -> tuple[str, Optional[dict]]:
    """有界修复（BoundedRepairLoop，1 轮）：确定性策略优先
    （relocate 重定位 / remap 改挂已有证据 / 非核心声明限定或删除），
    可选 llm_rewrite 做一次句子级改写（获得 claims/issues/drop_ids 上下文）。
    绝不改核心声明的语义，修复后必须通过调用方复检。"""
    try:
        evidence_index = {}
        for cit in citations or []:
            rec = records_resolver(cit) if records_resolver else None
            text = (rec.get("fb", "") or rec.get("b", "") or rec.get("as", "")
                    if rec else "") or cit.get("chunk_text", "") or cit.get("body_snippet", "")
            if text:
                evidence_index[cit.get("id")] = {"text": text[:600]}
        loop = BoundedRepairLoop(max_cycles=1)
        core_ids = {c.get("id") for c in claims_mapping.get("claims", [])
                    if c.get("is_core")}

        async def _regen_wrapper(draft: str, drop_ids=None):
            # BoundedRepairLoop 的注入契约是 (answer, drop_ids=...)；
            # 这里补齐 claims/issues 上下文再转交集成侧的 LLM 改写闭包。
            return await llm_rewrite(draft, drop_ids=drop_ids,
                                     claims=claims_mapping.get("claims", []),
                                     issues=issues or [])

        report = await loop.run(
            answer, claims_mapping, evidence_index=evidence_index,
            grounding_fn=None, retrieve_fn=None,
            regenerate_fn=_regen_wrapper if llm_rewrite is not None else None,
            core_claim_ids=core_ids)
        repaired = report.get("answer", answer)
        if repaired and repaired.strip() and repaired != answer:
            return repaired, dict(report)
        return answer, (dict(report) if report.get("actions") else None)
    except Exception as exc:  # noqa: BLE001
        print(f"[answer-chain] repair degraded: {exc.__class__.__name__}: {str(exc)[:120]}", flush=True)
        return answer, None


def build_boundary(answer_status: str, claims_mapping: dict, citations: list,
                   grounded_count: int) -> str:
    """校准弃权消息（T026 knowledge_boundary；UNSUPPORTED/PARTIALLY 时）。"""
    claims = (claims_mapping or {}).get("claims", [])
    req_map = {"SUPPORTED": "SUPPORTED", "PARTIALLY_SUPPORTED": "PARTIAL",
               "UNSUPPORTED": "MISSING"}
    if claims:
        requirements = [{"status": req_map.get(c.get("support_status", "UNSUPPORTED"),
                                                "MISSING"),
                         "text": c.get("text", "")} for c in claims[:8]]
    else:
        requirements = [{"status": "MISSING", "text": "（状态机未产出声明映射）"}]
    independent = len({c.get("source", "") for c in citations or [] if c.get("source")})
    coverage = assess_coverage(requirements=requirements,
                               evidence_count=grounded_count,
                               independent_groups=independent)
    supported_aspects = [c.get("text", "") for c in claims
                         if c.get("support_status") == "SUPPORTED"][:5]
    unsupported_aspects = [c.get("text", "") for c in claims
                           if c.get("support_status") != "SUPPORTED"][:5]
    return format_boundary_message(
        answer_status=KBStatus(answer_status),
        supported_aspects=supported_aspects,
        unsupported_aspects=unsupported_aspects,
        coverage_level=coverage)


async def run_answer_verification(
    query: str,
    answer: str,
    citations: list,
    *,
    claim_metadata: Optional[list] = None,
    records_resolver: Optional[Callable] = None,
    has_results: bool = True,
    is_relevant: bool = True,
    evidence_status: str = "unknown",
    flags: Optional[dict] = None,
    safety_scan: Optional[Callable] = None,
    llm_rewrite: Optional[Callable] = None,
) -> dict:
    """生成后全链核验（见模块头）。返回报告 dict，绝不抛异常——
    任一步失败都降级为对应 UNVERIFIED/缺省字段（旧 FAIL_SAFE 契约）。"""
    flags = flags or {}
    answer = (answer or "").strip()
    citations = citations or []
    claim_metadata = claim_metadata or []
    report: dict = {
        "version": ANSWER_CHAIN_VERSION,
        "refusal": False, "refusal_reason": "",
        "verification": {"status": "", "issues": [], "failure_reason": ""},
        "claim_map": {"claims": []},
        "numeric": {"checked": 0, "downgraded": 0, "worst": "NO_CLAIM_NUMBER"},
        "grounding": None,
        "independence": {},
        "coverage_gate": None,
        "repair": None,
        "answer_status": "UNVERIFIED",
        "stop_reason": "",
        "unsupported_major_claims": [],
        "boundary_message": "",
        "safety_hits": [],
    }
    try:
        # ── 五.2 拒答识别：库内无资料的短回答走 no_evidence 弃权 ──
        refusal, refusal_reason = detect_refusal(answer)
        report["refusal"], report["refusal_reason"] = refusal, refusal_reason

        # ── verify 覆盖面补齐（2026-09-30 钠离子电池回归）：生成前分类
        # 只盖 top-5（旧对齐），这里把其余可引用 chunk 批面补齐，让
        # verifier 的有效 chunk 集覆盖 [1..len(citations)]。──
        if (not refusal and answer and citations
                and flags.get("EPISTEMIC_ENABLED", True)
                and len(claim_metadata) < len(citations)):
            try:
                extra = await asyncio.wait_for(
                    classify_full_coverage(query, citations,
                                           len(claim_metadata)),
                    timeout=SUPPLEMENTAL_BUDGET + 10)
                if extra:
                    claim_metadata = list(claim_metadata) + extra
            except asyncio.TimeoutError:
                print("[answer-chain] supplemental classify budget exhausted",
                      flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[answer-chain] supplemental classify degraded: "
                      f"{exc.__class__.__name__}: {str(exc)[:120]}", flush=True)

        # ── T005 fail-safe 事实核验（LLM）──
        verification_status = ""
        if (not refusal and claim_metadata and answer
                and flags.get("FAIL_SAFE_VERIFY_ENABLED", True)):
            try:
                vr = await asyncio.wait_for(
                    verify_with_fail_safe(query, answer, claim_metadata),
                    timeout=VERIFY_BUDGET)
                verification_status = vr.status
                report["verification"] = {
                    "status": vr.status, "issues": list(vr.issues)[:8],
                    "failure_reason": vr.failure_reason or ""}
            except asyncio.TimeoutError:
                verification_status = VERIFY_UNVERIFIED
                report["verification"] = {"status": VERIFY_UNVERIFIED,
                                          "issues": [], "failure_reason": "timeout"}
            except Exception as exc:  # noqa: BLE001
                verification_status = VERIFY_UNVERIFIED
                report["verification"] = {"status": VERIFY_UNVERIFIED,
                                          "issues": [],
                                          "failure_reason": f"{exc.__class__.__name__}: {str(exc)[:160]}"}

        # ── T004 声明→引用映射（LLM，anchor 兜底）──
        claims_mapping: dict = {"claims": []}
        if (not refusal and answer and citations
                and flags.get("CLAIM_MAPPING_ENABLED", True)):
            try:
                claims_mapping = await asyncio.wait_for(
                    map_claims_to_citations(query, answer, citations),
                    timeout=MAPPING_TIMEOUT)
            except asyncio.TimeoutError:
                claims_mapping = {"claims": []}
                verification_status = VERIFY_UNVERIFIED if not verification_status else verification_status
                report["verification"]["failure_reason"] = (
                    report["verification"].get("failure_reason") or "claim_mapping timeout")
            except Exception as exc:  # noqa: BLE001
                claims_mapping = {"claims": []}
                report["verification"]["failure_reason"] = (
                    report["verification"].get("failure_reason") or
                    f"claim_mapping {exc.__class__.__name__}")

        report["claim_map"] = claims_mapping
        report["unsupported_major_claims"] = [
            c.get("id") for c in get_unsupported_major_claims(claims_mapping)]

        # 引用卡的 supports_claim_ids（旧 legacy 同款回填）
        cit_support = {c.get("id"): [] for c in citations}
        for claim in claims_mapping.get("claims", []):
            for ref in claim.get("supported_by", []) or []:
                cid = ref.get("citation_id")
                if cid in cit_support and ref.get("relation") in SUPPORTING_RELATIONS:
                    cit_support[cid].append(claim.get("id"))
        for cit in citations:
            cit["supports_claim_ids"] = cit_support.get(cit.get("id"), [])

        # ── 数值核验（确定性；矛盾声明降级 UNSUPPORTED）──
        if not refusal and claims_mapping.get("claims"):
            report["numeric"] = run_numeric_checks(
                claims_mapping, citations, records_resolver)

        # ── 溯源/独立性（T048）──
        report["independence"] = _attach_lineage(
            claims_mapping, citations, records_resolver)

        # ── 覆盖门（RT-023，确定性）──
        if not refusal and answer:
            try:
                report["coverage_gate"] = check_claim_coverage(answer, claims_mapping)
            except Exception:  # noqa: BLE001
                pass

        # ── T003 引用证据原文定位 ──
        if records_resolver is not None and flags.get("CITATION_GROUNDING_ENABLED", True):
            report["grounding"] = ground_citations(citations, records_resolver, query)

        # ── RT-026 有界修复（VERIFY_FAILED 时；五.1 修复能力）──
        if (verification_status == VERIFY_FAILED
                and flags.get("ANSWER_REPAIR_ENABLED", True)
                and claims_mapping.get("claims")):
            answer2, repair_report = await _repair_if_failed(
                query, answer, claims_mapping, citations, records_resolver,
                llm_rewrite, issues=report["verification"].get("issues") or [])
            report["repair"] = repair_report
            if repair_report and repair_report.get("answer") != answer:
                answer = repair_report["answer"]
                # 修复后复检一次（修复契约：改动必须通过复检）
                try:
                    vr2 = await asyncio.wait_for(
                        verify_with_fail_safe(query, answer, claim_metadata),
                        timeout=VERIFY_BUDGET)
                    verification_status = vr2.status
                    report["verification"] = {
                        "status": vr2.status, "issues": list(vr2.issues)[:8],
                        "failure_reason": vr2.failure_reason or "",
                        "recheck_after_repair": True}
                except Exception as exc:  # noqa: BLE001
                    verification_status = VERIFY_UNVERIFIED
                    report["verification"] = {
                        "status": VERIFY_UNVERIFIED, "issues": [],
                        "failure_reason": f"recheck {exc.__class__.__name__}",
                        "recheck_after_repair": True}
                report["answer"] = answer

        # ── T006 状态机定案（唯一状态权威）──
        status, stop_reason = determine_answer_status(
            has_results=bool(has_results and citations and not refusal),
            is_relevant=bool(is_relevant and not refusal),
            verification_status=verification_status,
            claim_mapping=claims_mapping)
        if refusal:
            stop_reason = refusal_reason
        report["answer_status"] = status.value if isinstance(status, AnswerStatus) else str(status)
        report["stop_reason"] = stop_reason

        # ── T026 校准弃权 ──
        grounded_count = sum(1 for c in citations
                             if c.get("grounding_status") in ("VALID", "FUZZY"))
        if report["answer_status"] in ("UNSUPPORTED", "PARTIALLY_SUPPORTED") \
                and flags.get("KNOWLEDGE_BOUNDARY_ENABLED", True):
            report["boundary_message"] = build_boundary(
                report["answer_status"], claims_mapping, citations, grounded_count)
            if refusal:
                report["boundary_message"] = (
                    "当前知识库中未找到支持该问题的证据；这只说明库内缺少资料，"
                    "不表示现实世界中该事实或对象不存在。"
                    + (f"\n\n{report['boundary_message']}" if report["boundary_message"] else ""))

        # ── 泄密面扫描（链路自有实现注入）──
        if safety_scan is not None:
            try:
                report["safety_hits"] = safety_scan(answer) or []
            except Exception:  # noqa: BLE001
                report["safety_hits"] = []
    except Exception as exc:  # noqa: BLE001 — 顶层兜底：核验永不阻断答案
        print(f"[answer-chain] FATAL degraded: {exc.__class__.__name__}: {str(exc)[:200]}", flush=True)
        report["answer_status"] = "UNVERIFIED"
        report["stop_reason"] = "answer_chain_exception"
        report["verification"]["failure_reason"] = f"{exc.__class__.__name__}: {str(exc)[:160]}"
    return report


def compact_for_payload(report: dict) -> dict:
    """done 事件里的精简形态（claim_map 展开是给审计用的，全量留在服务端
    日志；SSE payload 只带结论与有限明细）。"""
    if not report:
        return {}
    return {
        "version": report.get("version"),
        "answer_status": report.get("answer_status"),
        "stop_reason": report.get("stop_reason"),
        "refusal": report.get("refusal"),
        "verification": report.get("verification"),
        "numeric": report.get("numeric"),
        "grounding": report.get("grounding"),
        "claims_total": len((report.get("claim_map") or {}).get("claims", [])),
        "claims_supported": sum(1 for c in (report.get("claim_map") or {}).get("claims", [])
                                if c.get("support_status") == "SUPPORTED"),
        "unsupported_major_claims": report.get("unsupported_major_claims"),
        "coverage_gate": report.get("coverage_gate"),
        "repair": ({k: report["repair"][k] for k in
                    ("terminal_reason", "cycles_used", "regenerated", "unresolved_core_claims")}
                   if report.get("repair") else None),
        "boundary_message": report.get("boundary_message"),
        "safety_hits": report.get("safety_hits"),
    }

#!/usr/bin/env python3
"""检索编排层：tech-db legacy_hybrid 能力在 canonical-qa 的等价实现。

第七节问答能力迁移的检索侧收口。纯标准库（不依赖 fastapi/numpy/jieba），
server.py 与测试两侧共用同一实现，保证"测试过的行为 == 部署的行为"。

覆盖的 legacy_hybrid shipped flags（全部默认 ON，与旧系统 gate-3 缺省一致）：
  AGENTIC / TRACE / ROUTER / DECOMPOSITION / RERANKER /
  EVIDENCE_SELECTOR / EVIDENCE_GRADER / ITERATIVE_RETRIEVAL /
  PROVENANCE / TEMPORAL / ENTITY_RESOLUTION / SEMANTIC_GRAPH /
  CONTEXTUAL_CHUNKS / NUMERIC_FACTS / CLAIM_GROUNDING /
  FAIL_SAFE_VERIFY / CONTENT_SAFETY / CITATION_GROUNDING /
  CLAIM_MAPPING / ANSWER_STATUS / KNOWLEDGE_BOUNDARY
实验性 flags 默认 OFF（与 legacy_hybrid 回滚目标一致）：
  EXACT_GROUNDING / TERMINAL_RENDERER / EVIDENCE_PACKAGE / GRAPH_V2

环境变量覆盖：QA_<FLAG_NAME>=0/1（与旧系统 QA_ 前缀一致）。
"""
from __future__ import annotations

import os
import re
from collections import Counter

__all__ = [
    "SHIPPED_FLAG_NAMES", "EXPERIMENTAL_FLAG_NAMES", "feature_flags",
    "decompose_query", "extract_query_terms", "result_identity",
    "rrf_merge_rounds", "novelty_filter", "rerank_results",
    "match_entities", "graph_expand", "grade_evidence", "numeric_facts",
    "check_claims", "compute_answer_status", "boundary_note",
    "content_safety_scan", "safe_stage",
]

# ── Feature flags（legacy_hybrid profile）─────────────────────────────────
SHIPPED_FLAG_NAMES = (
    "AGENTIC_ENABLED", "TRACE_ENABLED", "ROUTER_ENABLED",
    "DECOMPOSITION_ENABLED", "RERANKER_ENABLED",
    "EVIDENCE_SELECTOR_ENABLED", "EVIDENCE_GRADER_ENABLED",
    "ITERATIVE_RETRIEVAL_ENABLED", "PROVENANCE_ENABLED",
    "TEMPORAL_ENABLED", "ENTITY_RESOLUTION_ENABLED",
    "SEMANTIC_GRAPH_ENABLED", "CONTEXTUAL_CHUNKS_ENABLED",
    "NUMERIC_FACTS_ENABLED", "CLAIM_GROUNDING_ENABLED",
    "FAIL_SAFE_VERIFY_ENABLED", "CONTENT_SAFETY_ENABLED",
    "CITATION_GROUNDING_ENABLED", "CLAIM_MAPPING_ENABLED",
    "ANSWER_STATUS_ENABLED", "KNOWLEDGE_BOUNDARY_ENABLED",
    # 五.1（2026-09-30）：答案侧真实核验链的两个开关。EPISTEMIC 在旧系统
    # 无 flag、legacy 路径恒开（仅预算熔断）；ANSWER_REPAIR 对应旧仓库
    # answer_repair.BoundedRepairLoop（RT-026）——legacy_hybrid 生产路径
    # 不改写答案，此处按五.1「修复/降级能力」要求接入，默认开但严格有界
    # （1 轮、确定性策略优先、失败即降级），QA_ANSWER_REPAIR_ENABLED=0 可关。
    "EPISTEMIC_ENABLED", "ANSWER_REPAIR_ENABLED",
)
EXPERIMENTAL_FLAG_NAMES = (
    "EXACT_GROUNDING_ENABLED", "TERMINAL_RENDERER_ENABLED",
    "EVIDENCE_PACKAGE_ENABLED", "GRAPH_V2_ENABLED",
)

_FLAG_ENV_PREFIX = "QA_"


def feature_flags(env: dict | None = None) -> dict:
    """legacy_hybrid 缺省 + QA_<NAME> 环境变量覆盖。"""
    env = os.environ if env is None else env
    flags = {name: True for name in SHIPPED_FLAG_NAMES}
    flags.update({name: False for name in EXPERIMENTAL_FLAG_NAMES})
    for name in (*SHIPPED_FLAG_NAMES, *EXPERIMENTAL_FLAG_NAMES):
        raw = str(env.get(_FLAG_ENV_PREFIX + name, "")).strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            flags[name] = True
        elif raw in {"0", "false", "no", "off"}:
            flags[name] = False
    return flags


def safe_stage(flags: dict, stage: str, fn, fallback):
    """FAIL_SAFE_VERIFY：单阶段失败只降级不拖垮整条检索链。"""
    if not flags.get("FAIL_SAFE_VERIFY_ENABLED", True):
        return fn()
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - 防御分支
        return fallback, {"stage": stage, "degraded": True, "error": exc.__class__.__name__}


# ── 查询处理：Router / Decomposition ─────────────────────────────────────
_SPLIT_RE = re.compile(r"[;；?？!！。\n]+|\s(?:和|与|及|以及|还有|对比|比较)\s")
_MAX_SUBQUERIES = 4
_MIN_SUBQUERY_CHARS = 2


def decompose_query(query: str, flags: dict) -> tuple[list[str], dict]:
    """DECOMPOSITION：确定性子查询拆分（不依赖 LLM，离线可用）。

    原查询始终保留为第一路；结构分隔符切出的片段（长度达标且非原查询
    子串重复）作为补充路。ROUTER 决定是否值得多路（单片段 = 不拆）。
    """
    base = (query or "").strip()
    trace: dict = {"router_enabled": bool(flags.get("ROUTER_ENABLED")), "decomposed": False,
                   "subqueries": [base] if base else []}
    if not base:
        return [], trace
    if not flags.get("DECOMPOSITION_ENABLED") or not flags.get("ROUTER_ENABLED"):
        return [base], trace
    parts: list[str] = []
    for raw in _SPLIT_RE.split(base):
        part = (raw or "").strip()
        if len(part) < _MIN_SUBQUERY_CHARS:
            continue
        if part == base:
            continue
        parts.append(part)
    parts = parts[:_MAX_SUBQUERIES - 1]
    if not parts:
        return [base], trace
    subqueries = [base, *parts]
    trace.update({"decomposed": True, "subqueries": subqueries})
    return subqueries, trace


_ASCI_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-+.]{1,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_QUERY_STOP = {"什么", "怎么", "如何", "哪些", "哪些有", "请问", "一下", "关于",
               "介绍", "情况", "最新", "目前", "现在", "数据库", "资料", "情报",
               "信息", "问题", "回答", "分析", "总结", "还有", "以及", "对比"}


def extract_query_terms(query: str, max_terms: int = 24) -> list[str]:
    """RERANKER 用查询词：ASCII 词 + CJK 双字组（确定性，替代 jieba 依赖）。"""
    query = query or ""
    terms: list[str] = []
    for m in _ASCI_WORD_RE.finditer(query):
        w = m.group(0).lower()
        if len(w) >= 2 and w not in terms:
            terms.append(w)
    cjk_spans = [m.group(0) for m in _CJK_RE.finditer(query)]
    for span in cjk_spans:
        if len(span) == 1:
            if span not in terms:
                terms.append(span)
            continue
        for i in range(len(span) - 1):
            gram = span[i:i + 2]
            if gram in _QUERY_STOP or gram in terms:
                continue
            terms.append(gram)
    return terms[:max_terms]


def _coverage(text: str, terms: list[str]) -> float:
    if not terms:
        return 0.0
    low = (text or "").lower()
    hit = sum(1 for t in terms if t and t in low)
    return hit / len(terms)


# ── 结果归并：ITERATIVE_RETRIEVAL / novelty 排除 ─────────────────────────
def result_identity(result: dict) -> tuple:
    """结果身份键：上传按 document_id+chunk_id，基线按 record_idx→url→标题。"""
    meta = result.get("meta") or {}
    if meta.get("kind") == "upload" and meta.get("document_id"):
        return ("upload", str(meta.get("document_id")), str(meta.get("chunk_id") or ""))
    rid = meta.get("record_id")
    if rid is not None:
        return ("record", str(rid))
    return ("bare", str(result.get("title", ""))[:80], str(result.get("date", "")),
            str(result.get("source", ""))[:40], str(result.get("url", "")))


def rrf_merge_rounds(rounds: list[list[dict]], k: int = 60, cap: int = 80) -> list[dict]:
    """ITERATIVE_RETRIEVAL：多路（子查询/图谱扩展）结果 RRF 归并。

    每一路内部已按序（分数降序）；跨路 RRF 权重累加。输出按 RRF 分降序，
    且 score 统一改写为 RRF 分：各路输入的 score 量纲可能不同（子查询路
    来自 rrf_fuse 的 RRF 分，图谱扩展路来自 bm25_search 的原始 BM25 分），
    原样保留会让重排先验跨量纲比较（一.6 隔离复现：原始 BM25 分 24~38 的
    图谱扩展项以 ~1000 倍先验淹没增量记录）。原始分存入 raw_score 留证。
    """
    acc: dict[tuple, dict] = {}
    for round_results in rounds:
        for rank, result in enumerate(round_results):
            key = result_identity(result)
            contrib = 1.0 / (k + rank + 1)
            if key in acc:
                acc[key]["_rrf"] += contrib
                best_raw = max(acc[key].get("score") or 0, result.get("score") or 0)
                acc[key]["score"] = best_raw
            else:
                merged = dict(result)
                merged["_rrf"] = contrib
                acc[key] = merged
    merged = sorted(acc.values(), key=lambda r: r.get("_rrf", 0), reverse=True)
    for item in merged:
        if "vec_score" not in item and "bm25_score" not in item:
            item["raw_score"] = item.get("score")
        item["score"] = round(float(item.get("_rrf", 0) or 0), 6)
    return merged[:cap]


def novelty_filter(results: list[dict], exclude_ids: list[str] | set[str] | None,
                   keep_floor: int = 5) -> tuple[list[dict], int, list[str]]:
    """novelty exclusion：历史已引用记录不重复召回（保底 keep_floor 条防饿死）。"""
    if not exclude_ids:
        return results, 0, []
    exclude = {str(e) for e in exclude_ids if str(e).strip()}
    if not exclude:
        return results, 0, []
    kept: list[dict] = []
    excluded_ids: list[str] = []
    for result in results:
        meta = result.get("meta") or {}
        rid = str(meta.get("document_id") or meta.get("record_id") or "")
        url = str(result.get("url", ""))
        title = str(result.get("title", ""))
        if rid and rid in exclude:
            excluded_ids.append(rid or title[:40])
            continue
        if url and url in exclude:
            excluded_ids.append(url)
            continue
        kept.append(result)
    if len(kept) < keep_floor:
        # 保底：排除导致结果不足时回补（保证 follow-up 不因排除饿死）
        kept = results
        return kept, 0, ["floor-restore"]
    return kept, len(excluded_ids), excluded_ids


# ── 重排：RERANKER / TEMPORAL / EVIDENCE_SELECTOR ────────────────────────
def _parse_year(date: str) -> int:
    m = re.search(r"(20\d{2})", date or "")
    return int(m.group(1)) if m else 0


def rerank_results(results: list[dict], query: str, flags: dict,
                   cap: int = 25) -> tuple[list[dict], dict]:
    """确定性重排：检索分先验 × 词覆盖 × 类别命中 × 新鲜度 × 精选加权。"""
    terms = extract_query_terms(query)
    trace: dict = {"terms": len(terms), "reranked": False}
    if not results:
        return results, trace
    scored: list[tuple[float, dict]] = []
    for result in results:
        prior = float(result.get("score") or 0)
        title = str(result.get("title", ""))
        category = str(result.get("category", ""))
        snippet = str(result.get("body_snippet", ""))
        cov = max(_coverage(title, terms), 0.0)
        cov_body = _coverage(snippet, terms) * 0.5
        cat_hit = 0.15 if any(t and t in category for t in terms) else 0.0
        fresh = 0.0
        if flags.get("TEMPORAL_ENABLED"):
            year = _parse_year(str(result.get("date", "")))
            if year:
                fresh = min(max((year - 2020) * 0.01, 0.0), 0.08)
        boost = 0.0
        meta = result.get("meta") or {}
        if meta.get("ai_picked"):
            boost = 0.05
        final = prior * (0.6 + 0.4 * min(cov + cov_body, 1.0)) + cat_hit + fresh + boost
        scored.append((final, result))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    ordered = [dict(r, rerank_score=round(s, 6)) for s, r in scored]
    if not flags.get("RERANKER_ENABLED"):
        ordered = list(results)
        trace["reranked"] = False
        return ordered[:cap], trace
    trace["reranked"] = True
    trace["top_rerank_score"] = round(scored[0][0], 6) if scored else 0.0
    # EVIDENCE_SELECTOR：截断到证据窗（cap 即 selector 窗口）
    return ordered[:cap], trace


# ── 实体 / 关系检索：ENTITY_RESOLUTION / SEMANTIC_GRAPH ──────────────────
def match_entities(query: str, node_labels: list[tuple[str, str, int]],
                   max_entities: int = 6) -> list[dict]:
    """查询词 ↔ 图谱节点标签匹配。node_labels: [(id, label, degree)]。

    精确包含匹配，按 degree 降序、标签长度升序（更具体的标签优先）。
    """
    if not query or not node_labels:
        return []
    terms = extract_query_terms(query, max_terms=40)
    long_terms = sorted({t for t in terms if len(t) >= 2}, key=len, reverse=True)
    hits: list[dict] = []
    seen: set[str] = set()
    q = query
    for node_id, label, degree in node_labels:
        lab = str(label or "")
        if len(lab) < 2 or lab in seen:
            continue
        if lab in q or any(t in lab for t in long_terms[:12]):
            seen.add(lab)
            hits.append({"id": str(node_id), "label": lab, "degree": int(degree or 0)})
        if len(hits) >= max_entities:
            break
    hits.sort(key=lambda h: (-h["degree"], len(h["label"])))
    return hits[:max_entities]


def graph_expand(entities: list[dict], adjacency: dict[str, list[tuple[str, str]]],
                  max_neighbors: int = 8, max_hops: int = 1) -> tuple[list[str], list[dict]]:
    """SEMANTIC_GRAPH：命中实体沿边扩展 1 跳邻居标签（ relations 参与检索）。

    adjacency: node_id → [(neighbor_label, edge_label)]。
    返回 (邻居标签列表, 展开路径 trace)。
    """
    labels: list[str] = []
    paths: list[dict] = []
    seen: set[str] = set()
    for ent in entities:
        nid = ent.get("id")
        for neighbor_label, edge_label in (adjacency.get(nid) or [])[:max_neighbors]:
            lab = str(neighbor_label or "").strip()
            if len(lab) < 2 or lab in seen:
                continue
            seen.add(lab)
            labels.append(lab)
            paths.append({"from": ent.get("label"), "relation": str(edge_label or ""),
                          "to": lab})
            if len(labels) >= max_neighbors * max_hops:
                return labels[:max_neighbors], paths
    return labels[:max_neighbors], paths


# ── 证据评估：EVIDENCE_GRADER / NUMERIC_FACTS ────────────────────────────
def grade_evidence(results: list[dict], query: str) -> dict:
    """证据充足性门控：sufficient / partial / insufficient。

    分数尺度自适应：不同检索路（向量相似度 0-1 / BM25 词频 0-N）量纲不同，
    strong 判定用相对强度（≥ 0.4 × 顶分），不假设绝对阈值。
    """
    if not results:
        return {"status": "insufficient", "count": 0, "avg_score": 0.0,
                "term_coverage": 0.0}
    scores = [float(r.get("score") or 0) for r in results]
    avg = sum(scores) / len(scores)
    terms = extract_query_terms(query)
    top_text = " ".join(str(r.get("title", "")) + str(r.get("body_snippet", ""))
                        for r in results[:5])
    coverage = _coverage(top_text, terms)
    max_score = max(scores) or 0.0
    strong = sum(1 for s in scores if s >= 0.4 * max_score)
    if strong >= min(3, len(scores)) and (coverage >= 0.25 or (avg >= 0.35 and max_score <= 1.5)):
        status = "sufficient"
    else:
        status = "partial"
    return {"status": status, "count": len(results), "avg_score": round(avg, 4),
            "term_coverage": round(coverage, 4), "strong_count": strong}


_NUM_UNIT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(万吨|亿|万元|亿元|%|％|GWh|TWh|kWh|MW|GW|kW|Wh/kg|Wh/L|kt|Mt|ppm|nm|mm|μm|um|kg|t|年|倍|元|美元|立方米|平方米)"
)


def numeric_facts(texts: list[str], max_facts: int = 12) -> list[str]:
    """NUMERIC_FACTS：证据中的 数字+单位 事实点（确定性抽取，供追溯）。"""
    facts: list[str] = []
    seen: Counter = Counter()
    for text in texts:
        for m in _NUM_UNIT_RE.finditer(text or ""):
            fact = "".join(m.groups())
            if seen[fact]:
                continue
            seen[fact] += 1
            facts.append(fact)
            if len(facts) >= max_facts:
                return facts
    return facts


# ── 答案侧：CITATION_GROUNDING / CLAIM_MAPPING / ANSWER_STATUS /
#    KNOWLEDGE_BOUNDARY / CONTENT_SAFETY ──────────────────────────────────
_MARK_RE = re.compile(r"\[(\d{1,3})\]")
_SENT_SPLIT_RE = re.compile(r"[。！？!?\n]+")
_ASSERT_MARKERS = ("为", "是", "达", "占", "增长", "下降", "提升", "下降", "预计", "将",
                   "显示", "根据", "指出", "认为", "突破", "超过", "约")


def check_claims(answer: str, citation_count: int) -> dict:
    """CITATION_GROUNDING + CLAIM_MAPPING：引用标注核验与句子级 claim 映射。"""
    answer = answer or ""
    marks = [int(m) for m in _MARK_RE.findall(answer)]
    invalid = sorted({m for m in marks if m < 1 or m > max(citation_count, 0)})
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(answer) if s.strip()]
    factual = [s for s in sentences if any(mk in s for mk in _ASSERT_MARKERS) and len(s) >= 8]
    cited_sentences = sum(1 for s in factual if _MARK_RE.search(s))
    mapping = [{"claim": s[:80], "citation": sorted({int(m) for m in _MARK_RE.findall(s)})}
               for s in factual if _MARK_RE.search(s)][:20]
    return {
        "citation_marks": len(marks),
        "invalid_markers": invalid,
        "factual_sentences": len(factual),
        "cited_sentences": cited_sentences,
        "cited_ratio": round(cited_sentences / len(factual), 4) if factual else None,
        "claim_citation_map": mapping,
    }


def compute_answer_status(used_citation_count: int, evidence_status: str,
                          claim_check: dict, citation_count: int) -> str:
    """ANSWER_STATUS：verified / partial / insufficient。"""
    if not citation_count:
        return "insufficient"
    if used_citation_count and evidence_status == "sufficient":
        ratio = claim_check.get("cited_ratio")
        if ratio is None or ratio >= 0.4:
            return "verified"
        return "partial"
    if used_citation_count:
        return "partial"
    return "insufficient"


def boundary_note(status: str, evidence_status: str) -> str | None:
    """KNOWLEDGE_BOUNDARY：证据薄弱时给出边界声明（不伪造完整答案）。"""
    if status == "insufficient" or evidence_status == "insufficient":
        return ("⚠️ 知识边界提示：当前数据库中与该问题直接相关的情报不足，"
                "以上内容可能不完整；建议补充检索条件或等待后续情报更新。")
    if status == "partial":
        return ("⚠️ 知识边界提示：以上回答仅部分覆盖数据库现有证据，"
                "关键结论请核对引用原文。")
    return None


_PRIVATE_PATTERNS = (
    ("local_path", re.compile(r"(?<![\w/])(/home/|/root/|C:\\\\Users\\\\)[^\s\"']{2,}")),
    ("api_key", re.compile(r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|gh_[A-Za-z0-9]{20,})")),
    ("internal_host", re.compile(r"https?://(localhost|127\.0\.0\.1|host\.docker\.internal)[^\s]*")),
)


def content_safety_scan(text: str) -> list[dict]:
    """CONTENT_SAFETY：答案泄密面扫描（本地路径/密钥/内网地址）。"""
    hits: list[dict] = []
    for name, pattern in _PRIVATE_PATTERNS:
        m = pattern.search(text or "")
        if m:
            hits.append({"kind": name, "sample": m.group(0)[:24]})
    return hits

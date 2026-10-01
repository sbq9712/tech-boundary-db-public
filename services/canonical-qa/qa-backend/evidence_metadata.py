"""证据角色推断（2026-09-30，五.1 移植）。

从旧仓库 scripts/enrich_evidence_metadata.py 原样移植 infer_evidence_role
（claim_mapping.attach_span_lineage / claim_independence 需要它判定引用的
evidence_role：self_reported / commentary / independent / unknown）。
"""
from __future__ import annotations


def infer_evidence_role(record: dict) -> str:
    """Infer evidence role from provenance plus the current triage taxonomy."""
    tag = record.get("tg", "")
    source = (record.get("a", "") or record.get("s", "")).lower()

    if tag in {
        "知识资产", "工程与产业化", "企业经营、合作与资本", "人才与组织动态",
        "产业进展", "技术突破",
    } and source:
        return "self_reported"

    if tag in {
        "观点与交流", "分析类", "新闻/评论/观点", "观点评论", "行业观察",
    }:
        return "commentary"

    if record.get("independence_verified") is True and record.get("provenance_root_id"):
        return "independent"

    return "unknown"


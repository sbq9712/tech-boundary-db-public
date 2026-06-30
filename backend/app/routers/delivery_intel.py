from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user

router = APIRouter(tags=["delivery-intel"], dependencies=[Depends(get_current_user)])

DELIVERY_VIEWS = Path(os.getenv("DELIVERY_VIEWS_PATH", "/app/delivery_views"))
_CACHE: list[dict] | None = None

# taxonomy_path 第3段 → 领域标签
DOMAIN_MAP = {
    "能量存储": "能量存储",
    "能源测": "发电技术",
    "有机物（碳循环）": "有机物循环",
    "无机物": "无机物",
    "资源处理": "资源处理",
}

# source_type → 中文标签
SOURCE_TYPE_LABEL = {
    "literature_summary": "学术论文",
    "news_original":      "产业新闻",
    "wechat_article":     "微信文章",
    "unknown":            "其他",
}


def _load() -> list[dict]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    p = DELIVERY_VIEWS / "intelligence_master_table.jsonl"
    if not p.exists():
        return []
    rows: list[dict] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    _CACHE = rows
    return rows


def _domain_of(row: dict) -> str:
    """Extract the 3rd segment of xmind_taxonomy_path as domain key."""
    parts = [p.strip() for p in (row.get("xmind_taxonomy_path") or "").split(">")]
    return parts[2] if len(parts) >= 3 else ""


@router.get("/delivery-intel/meta")
def get_meta() -> dict:
    """Return available domain and source_type values for filter dropdowns."""
    rows = _load()
    domains: set[str] = set()
    source_types: set[str] = set()
    for r in rows:
        d = _domain_of(r)
        if d:
            domains.add(d)
        st = r.get("source_type", "")
        if st:
            source_types.add(st)
    return {
        "domains": [
            {"key": k, "label": DOMAIN_MAP.get(k, k)}
            for k in sorted(domains)
        ],
        "source_types": [
            {"key": k, "label": SOURCE_TYPE_LABEL.get(k, k)}
            for k in sorted(source_types)
        ],
    }


@router.get("/delivery-intel")
def list_delivery_intel(
    q: str = Query("", alias="q"),
    leaf: str = Query("", alias="leaf"),
    domain: str = Query("", alias="domain"),
    source_type: str = Query("", alias="source_type"),
    limit: int = Query(200),
    offset: int = Query(0),
) -> dict:
    """
    Filter delivery_views intelligence_master_table.jsonl.
      ?q=SOFC           – full-text in title/path/leaf
      ?leaf=燃料电池    – exact leaf_title (from industry map)
      ?domain=能量存储  – 3rd segment of taxonomy_path
      ?source_type=literature_summary
    """
    rows = _load()

    if leaf:
        rows = [r for r in rows if r.get("leaf_title", "") == leaf]
    else:
        if q:
            q_lower = q.lower()
            rows = [
                r for r in rows
                if q_lower in (r.get("title") or "").lower()
                or q_lower in (r.get("xmind_taxonomy_path") or "").lower()
                or q_lower in (r.get("leaf_title") or "").lower()
                or q_lower in (r.get("source_name") or "").lower()
            ]
        if domain:
            rows = [r for r in rows if _domain_of(r) == domain]
        if source_type:
            rows = [r for r in rows if r.get("source_type", "") == source_type]

    total = len(rows)
    page = rows[offset: offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "items": [_to_out(r) for r in page]}


@router.get("/delivery-intel/{source_id}")
def get_delivery_intel(source_id: str) -> dict:
    rows = _load()
    for r in rows:
        if r.get("source_id") == source_id:
            return _to_out(r)
    raise HTTPException(404, "Intel item not found")


def _to_out(r: dict) -> dict:
    st = r.get("source_type", "")
    return {
        "id": r.get("source_id", ""),
        "title": r.get("title", "(无标题)"),
        "taxonomy_path": r.get("xmind_taxonomy_path", ""),
        "domain": _domain_of(r),
        "domain_label": DOMAIN_MAP.get(_domain_of(r), _domain_of(r)),
        "leaf_title": r.get("leaf_title", ""),
        "source_type": st,
        "source_type_label": SOURCE_TYPE_LABEL.get(st, st),
        "source_name": r.get("source_name", ""),
        "publish_date": r.get("publish_date", ""),
        "url": r.get("url", ""),
        "key_metric": r.get("key_metric", ""),
        "metric_type": r.get("metric_type", ""),
        "value_raw": r.get("value_raw", ""),
        "value_numeric": r.get("value_numeric", ""),
        "unit": r.get("unit", ""),
        "object_name": r.get("object_name", ""),
        "evidence_text": r.get("evidence_text", ""),
        "semantic_evidence": r.get("semantic_evidence", ""),
        "confidence": r.get("confidence", ""),
        "need_human_review": r.get("need_human_review", False),
    }

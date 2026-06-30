from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user

router = APIRouter(tags=["delivery-intel"], dependencies=[Depends(get_current_user)])

DELIVERY_VIEWS = Path(os.getenv("DELIVERY_VIEWS_PATH", "/app/delivery_views"))
_CACHE: list[dict] | None = None

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
    """3rd segment of taxonomy_path (group level)."""
    parts = [p.strip() for p in (row.get("xmind_taxonomy_path") or "").split(">")]
    return parts[2] if len(parts) >= 3 else ""


@router.get("/delivery-intel/meta")
def get_meta() -> dict:
    """
    Return distinct leaf_title values and source_type values for filter dropdowns.
    leaf_titles are sorted by count descending so common ones appear first.
    """
    from collections import Counter
    rows = _load()
    leaf_counter: Counter = Counter()
    source_types: set[str] = set()
    for r in rows:
        lt = r.get("leaf_title", "")
        if lt:
            leaf_counter[lt] += 1
        st = r.get("source_type", "")
        if st:
            source_types.add(st)

    return {
        # leaf_titles ordered by frequency
        "leaf_titles": [
            {"key": lt, "label": lt, "count": cnt}
            for lt, cnt in leaf_counter.most_common()
        ],
        # source_types with Chinese labels
        "source_types": [
            {"key": k, "label": SOURCE_TYPE_LABEL.get(k, k)}
            for k in sorted(source_types)
        ],
    }


@router.get("/delivery-intel")
def list_delivery_intel(
    q: str = Query("", alias="q"),
    leaf: str = Query("", alias="leaf"),
    source_type: str = Query("", alias="source_type"),
    limit: int = Query(200),
    offset: int = Query(0),
) -> dict:
    """
    Filter intelligence_master_table.jsonl.
      ?q=SOFC             – full-text in title/path/leaf
      ?leaf=燃料电池      – exact leaf_title match
      ?source_type=literature_summary
    Filters combine (AND logic).
    """
    rows = _load()

    if leaf:
        rows = [r for r in rows if r.get("leaf_title", "") == leaf]
    if q:
        q_lower = q.lower()
        rows = [
            r for r in rows
            if q_lower in (r.get("title") or "").lower()
            or q_lower in (r.get("xmind_taxonomy_path") or "").lower()
            or q_lower in (r.get("leaf_title") or "").lower()
            or q_lower in (r.get("source_name") or "").lower()
        ]
    if source_type:
        rows = [r for r in rows if r.get("source_type", "") == source_type]

    total = len(rows)
    page = rows[offset: offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_to_out(r) for r in page],
    }


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

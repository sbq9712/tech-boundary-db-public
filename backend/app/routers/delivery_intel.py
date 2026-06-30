from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import get_current_user

router = APIRouter(tags=["delivery-intel"], dependencies=[Depends(get_current_user)])

DELIVERY_VIEWS = Path(os.getenv("DELIVERY_VIEWS_PATH", "/app/delivery_views"))
_CACHE: list[dict] | None = None


def _load() -> list[dict]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    p = DELIVERY_VIEWS / "intelligence_master_table.jsonl"
    if not p.exists():
        return []
    rows = []
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


@router.get("/delivery-intel")
def list_delivery_intel(
    q: str = Query("", alias="q"),
    leaf: str = Query("", alias="leaf"),
    limit: int = Query(200),
) -> dict:
    """
    Search delivery_views intelligence_master_table.jsonl.
    Supports:
      ?q=SOFC            – full-text search in title + taxonomy path
      ?leaf=SOFC电解槽   – exact leaf_title match (from industry map)
    """
    rows = _load()

    if leaf:
        rows = [r for r in rows if r.get("leaf_title", "") == leaf]
    elif q:
        q_lower = q.lower()
        rows = [
            r for r in rows
            if q_lower in (r.get("title") or "").lower()
            or q_lower in (r.get("xmind_taxonomy_path") or "").lower()
            or q_lower in (r.get("leaf_title") or "").lower()
            or q_lower in (r.get("source_name") or "").lower()
        ]

    rows = rows[:limit]

    return {
        "total": len(rows),
        "items": [_to_out(r) for r in rows],
    }


@router.get("/delivery-intel/{source_id}")
def get_delivery_intel(source_id: str) -> dict:
    """Get a single intel item by source_id."""
    rows = _load()
    for r in rows:
        if r.get("source_id") == source_id:
            return _to_out(r)
    from fastapi import HTTPException
    raise HTTPException(404, "Intel item not found")


def _to_out(r: dict) -> dict:
    return {
        "id": r.get("source_id", ""),
        "title": r.get("title", "(无标题)"),
        "taxonomy_path": r.get("xmind_taxonomy_path", ""),
        "leaf_title": r.get("leaf_title", ""),
        "source_type": r.get("source_type", ""),
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

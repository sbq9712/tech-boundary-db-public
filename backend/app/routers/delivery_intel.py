from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user

router = APIRouter(tags=["delivery-intel"], dependencies=[Depends(get_current_user)])

DELIVERY_VIEWS = Path(os.getenv("DELIVERY_VIEWS_PATH", "/app/delivery_views"))
BREADTH_DATA = Path(os.getenv("BREADTH_DATA_PATH", "/app/breadth_data"))
_CACHE: list[dict] | None = None
_BREADTH_COUNTS_CACHE: tuple[tuple, list[dict], str] | None = None

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


def _breadth_manifest_meta(data_dir: Path) -> dict:
    inline_path = data_dir / "processed" / "manifest-data.js"
    if inline_path.exists():
        raw = inline_path.read_text(encoding="utf-8")
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end >= start:
            try:
                return json.loads(raw[start:end + 1]).get("meta", {})
            except json.JSONDecodeError:
                pass
    manifest_path = data_dir / "processed" / "manifest.json"
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8")).get("meta", {})
        except json.JSONDecodeError:
            pass
    return {}


def _breadth_data_signature(data_dir: Path) -> tuple:
    meta = _breadth_manifest_meta(data_dir)
    data_version = str(meta.get("data_version", ""))
    if data_version:
        return ("data_version", data_version)
    files = sorted(data_dir.glob("processed/lite-part-*.js"))
    return tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in files)


def _breadth_source_signature(data_dir: Path) -> list[list[str | int]]:
    return [
        [p.name, p.stat().st_size]
        for p in sorted(data_dir.glob("processed/lite-part-*.js"))
    ]


def _load_breadth_category_counts() -> tuple[list[dict], str]:
    """Count the same records shown by breadth tracking, grouped by full path.

    The breadth page defaults to ``aicurated`` and hides duplicate rows and
    cluster children outside crawl mode. Keeping every level in the snapshot
    makes the counting rule explicit while ``count`` remains the default view.
    The file signature invalidates the in-process cache after an upstream sync.
    """
    global _BREADTH_COUNTS_CACHE
    signature = _breadth_data_signature(BREADTH_DATA)
    if not signature:
        return [], ""
    if _BREADTH_COUNTS_CACHE and _BREADTH_COUNTS_CACHE[0] == signature:
        return _BREADTH_COUNTS_CACHE[1], _BREADTH_COUNTS_CACHE[2]

    manifest_meta = _breadth_manifest_meta(BREADTH_DATA)
    data_version = str(manifest_meta.get("data_version", ""))
    snapshot_path = BREADTH_DATA / "processed" / "category-counts.json"
    if snapshot_path.exists():
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot_valid = (
                snapshot.get("data_version") == data_version
                if data_version
                else snapshot.get("source_signature") == _breadth_source_signature(BREADTH_DATA)
            )
            if snapshot_valid:
                result = snapshot.get("categories", [])
                processed_at = str(snapshot.get("processed_at", ""))
                _BREADTH_COUNTS_CACHE = (signature, result, processed_at)
                return result, processed_at
        except (OSError, json.JSONDecodeError):
            pass

    counts: dict[str, Counter] = defaultdict(Counter)
    for shard in sorted(BREADTH_DATA.glob("processed/lite-part-*.js")):
        raw = shard.read_text(encoding="utf-8")
        marker = ".push("
        start = raw.find(marker)
        end = raw.rfind(");")
        if start < 0 or end < 0:
            continue
        try:
            records = json.loads(raw[start + len(marker):end])
        except json.JSONDecodeError:
            continue
        for row in records:
            category = str(row.get("c") or "").strip()
            if not category or category == "\u4e0d\u76f8\u5173":
                continue
            level_counts = counts[category]
            level_counts["crawl"] += 1
            if row.get("cp") == 1 or bool(row.get("dp")):
                continue
            level_counts["filtered"] += 1
            if row.get("aip") == 1:
                level_counts["aicurated"] += 1
            level = row.get("lv") or 0
            if level >= 1:
                level_counts["curated"] += 1
            if level >= 2:
                level_counts["key"] += 1
            if level >= 3:
                level_counts["alert"] += 1

    processed_at = str(manifest_meta.get("processed_at", ""))

    result = [
        {
            "path": path,
            "label": path.rsplit("/", 1)[-1],
            "count": level_counts["aicurated"],
            "counts": {key: level_counts[key] for key in ("crawl", "filtered", "aicurated", "curated", "key", "alert")},
        }
        for path, level_counts in sorted(counts.items())
    ]
    _BREADTH_COUNTS_CACHE = (signature, result, processed_at)
    return result, processed_at


@router.get("/delivery-intel/meta")
def get_meta() -> dict:
    """
    Return distinct leaf_title values and source_type values for filter dropdowns.
    leaf_titles are sorted by count descending so common ones appear first.
    """
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

    category_counts, breadth_processed_at = _load_breadth_category_counts()
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
        "category_counts": category_counts,
        "category_count_level": "aicurated",
        "breadth_processed_at": breadth_processed_at,
    }


@router.get("/delivery-intel/category-counts")
def get_category_counts() -> dict:
    category_counts, breadth_processed_at = _load_breadth_category_counts()
    return {
        "category_counts": category_counts,
        "category_count_level": "aicurated",
        "breadth_processed_at": breadth_processed_at,
    }


@router.get("/delivery-intel")
def list_delivery_intel(
    q: str = Query("", alias="q"),
    leaf: str = Query("", alias="leaf"),
    source_type: str = Query("", alias="source_type"),
    alert: str = Query("", alias="alert"),
    item: str = Query("", alias="item"),
    limit: int = Query(200),
    offset: int = Query(0),
) -> dict:
    """
    Filter intelligence_master_table.jsonl.
      ?q=SOFC             – full-text in title/path/leaf
      ?leaf=燃料电池      – exact leaf_title match
      ?source_type=literature_summary
      ?alert=active       – same alert candidate rows used by home portal
      ?item=source_id     – focus one broad-tracking row
    Filters combine (AND logic).
    """
    rows = _load()

    if item:
        rows = [r for r in rows if r.get("source_id") == item]
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
    if alert:
        rows = [r for r in rows if _alert_active(r)]

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


def _alert_active(r: dict) -> bool:
    return r.get("alert_status") == "active" or bool(r.get("need_human_review"))


def _alert_level(r: dict) -> str:
    if r.get("alert_color"):
        return r["alert_color"]
    confidence = (r.get("confidence") or "").lower()
    if confidence == "high":
        return "high"
    if confidence == "medium":
        return "orange"
    return "normal"


def _alert_body(r: dict) -> str:
    return (
        r.get("alert_body")
        or r.get("semantic_evidence")
        or r.get("evidence_text")
        or r.get("key_metric")
        or ""
    )


def _to_out(r: dict) -> dict:
    st = r.get("source_type", "")
    source_id = r.get("source_id", "")
    active = _alert_active(r)
    title = r.get("title", "(无标题)")
    return {
        "id": source_id,
        "title": title,
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
        "alert_status": "active" if active else "none",
        "alert_title": r.get("alert_title") or title,
        "alert_body": _alert_body(r),
        "alert_color": _alert_level(r) if active else "normal",
        "alert_time": r.get("publish_date", ""),
        "target_url": f"#breadth?alert=active&item={source_id}" if active and source_id else "",
    }

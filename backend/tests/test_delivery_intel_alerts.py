from app.routers import delivery_intel
import json


def test_delivery_intel_alert_filter_returns_same_source_rows(monkeypatch):
    rows = [
        {
            "source_id": "src-alert",
            "title": "AIDC 800VDC 导入",
            "leaf_title": "算力能源基础设施",
            "xmind_taxonomy_path": "AI与智能科技>AI硬件层>算力能源基础设施",
            "source_type": "news_original",
            "publish_date": "2026-07-12",
            "url": "https://example.com/aidc",
            "confidence": "high",
            "need_human_review": True,
            "semantic_evidence": "800VDC 架构升级触发人工复核",
        },
        {
            "source_id": "src-normal",
            "title": "普通情报",
            "leaf_title": "芯片",
            "xmind_taxonomy_path": "AI与智能科技>AI硬件层>芯片",
            "source_type": "news_original",
            "need_human_review": False,
        },
    ]
    monkeypatch.setattr(delivery_intel, "_load", lambda: rows)

    payload = delivery_intel.list_delivery_intel(q="", leaf="", source_type="", alert="active", item="", limit=50, offset=0)

    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["id"] == "src-alert"
    assert item["alert_status"] == "active"
    assert item["alert_title"] == "AIDC 800VDC 导入"
    assert item["alert_body"] == "800VDC 架构升级触发人工复核"
    assert item["target_url"] == "#breadth?alert=active&item=src-alert"


def test_breadth_category_counts_match_default_page_rules(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    rows = [
        {"c": "AI与智能科技/AI硬件层/芯片", "aip": 1},
        {"c": "AI与智能科技/AI硬件层/芯片", "aip": 1, "dp": 1},
        {"c": "AI与智能科技/AI硬件层/芯片", "aip": 1, "cp": 1},
        {"c": "通用技术/催化剂", "lv": 2},
        {"c": "不相关", "aip": 1},
    ]
    (processed / "lite-part-0.js").write_text(
        "window.__LITE_PARTS__=window.__LITE_PARTS__||[];window.__LITE_PARTS__.push(" + json.dumps(rows, ensure_ascii=False) + ");",
        encoding="utf-8",
    )
    (processed / "manifest.json").write_text(
        json.dumps({"meta": {"processed_at": "2026-07-20T00:00:00Z"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(delivery_intel, "BREADTH_DATA", tmp_path)
    monkeypatch.setattr(delivery_intel, "_BREADTH_COUNTS_CACHE", None)

    counts, processed_at = delivery_intel._load_breadth_category_counts()
    by_path = {item["path"]: item for item in counts}

    chip = by_path["AI与智能科技/AI硬件层/芯片"]
    assert chip["counts"]["crawl"] == 3
    assert chip["counts"]["filtered"] == 1
    assert chip["counts"]["aicurated"] == 1
    assert chip["count"] == 1
    assert by_path["通用技术/催化剂"]["counts"]["key"] == 1
    assert "不相关" not in by_path
    assert processed_at == "2026-07-20T00:00:00Z"


def test_breadth_category_counts_use_matching_snapshot(tmp_path, monkeypatch):
    processed = tmp_path / "processed"
    processed.mkdir()
    shard = processed / "lite-part-0.js"
    shard.write_text("this is deliberately not parseable", encoding="utf-8")
    expected = [{"path": "通用技术/催化剂", "label": "催化剂", "count": 7, "counts": {}}]
    (processed / "category-counts.json").write_text(
        json.dumps({
            "source_signature": [[shard.name, shard.stat().st_size]],
            "processed_at": "2026-07-20T01:00:00Z",
            "categories": expected,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(delivery_intel, "BREADTH_DATA", tmp_path)
    monkeypatch.setattr(delivery_intel, "_BREADTH_COUNTS_CACHE", None)

    counts, processed_at = delivery_intel._load_breadth_category_counts()

    assert counts == expected
    assert processed_at == "2026-07-20T01:00:00Z"

#!/usr/bin/env python3
"""Build the small category-count snapshot consumed by the portal API."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "breadth" / "data"
LEVELS = ("crawl", "filtered", "aicurated", "curated", "key", "alert")


def source_signature(data_dir: Path) -> list[list[str | int]]:
    return [
        [path.name, path.stat().st_size]
        for path in sorted(data_dir.glob("processed/lite-part-*.js"))
    ]


def read_shard(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    marker = ".push("
    start = raw.find(marker)
    end = raw.rfind(");")
    if start < 0 or end < 0:
        raise ValueError(f"Unsupported lite shard wrapper: {path}")
    return json.loads(raw[start + len(marker):end])


def manifest_meta(data_dir: Path) -> dict:
    inline_path = data_dir / "processed" / "manifest-data.js"
    if inline_path.exists():
        raw = inline_path.read_text(encoding="utf-8")
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end >= start:
            return json.loads(raw[start:end + 1]).get("meta", {})
    manifest_path = data_dir / "processed" / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8")).get("meta", {})
    return {}


def build_snapshot(data_dir: Path) -> dict:
    counts: dict[str, Counter] = defaultdict(Counter)
    record_total = 0
    for shard in sorted(data_dir.glob("processed/lite-part-*.js")):
        for row in read_shard(shard):
            record_total += 1
            category = str(row.get("c") or "").strip()
            if not category or category == "\u4e0d\u76f8\u5173":
                continue
            category_counts = counts[category]
            category_counts["crawl"] += 1
            if row.get("cp") == 1 or bool(row.get("dp")):
                continue
            category_counts["filtered"] += 1
            if row.get("aip") == 1:
                category_counts["aicurated"] += 1
            level = row.get("lv") or 0
            if level >= 1:
                category_counts["curated"] += 1
            if level >= 2:
                category_counts["key"] += 1
            if level >= 3:
                category_counts["alert"] += 1

    meta = manifest_meta(data_dir)
    processed_at = str(meta.get("processed_at", ""))
    categories = [
        {
            "path": path,
            "label": path.rsplit("/", 1)[-1],
            "count": values["aicurated"],
            "counts": {level: values[level] for level in LEVELS},
        }
        for path, values in sorted(counts.items())
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "processed_at": processed_at,
        "data_version": str(meta.get("data_version", "")),
        "record_total": record_total,
        "default_level": "aicurated",
        "source_signature": source_signature(data_dir),
        "categories": categories,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    output = args.data_dir / "processed" / "category-counts.json"
    snapshot = build_snapshot(args.data_dir)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}: {snapshot['record_total']} records, {len(snapshot['categories'])} categories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "breadth" / "data"


def part_number(path: Path) -> int:
    match = re.search(r"lite-part-(\d+)\.js$", path.name)
    return int(match.group(1)) if match else 0


def load_part(path: Path) -> list[dict]:
    source = path.read_text(encoding="utf-8")
    marker = ".push("
    start = source.index(marker) + len(marker)
    end = source.rfind(");")
    return json.loads(source[start:end])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    processed = args.data_dir / "processed"
    output = processed / "alert-records.json"

    manifest = json.loads((processed / "manifest.json").read_text(encoding="utf-8"))
    generated_at = manifest.get("meta", {}).get("processed_at", "")

    raw_records: list[dict] = []
    for path in sorted(processed.glob("lite-part-*.js"), key=part_number):
        raw_records.extend(load_part(path))

    alerts = [
        {
            "title": row.get("t", ""),
            "published_at": row.get("d", ""),
            "alert_created_at": generated_at,
            "category": row.get("c", "") or "未分类",
            "domain_name": (row.get("c", "") or "未分类").split("/")[-1],
            "tag": row.get("tg", ""),
            "topic": row.get("tp", ""),
            "alert_reason": row.get("wr") or "",
            "reviewer_comment": " · ".join(
                value for value in (row.get("tg", ""), row.get("tp", "")) if value
            ) or "高信号变化",
            "alert_body": row.get("as", "") or row.get("b", ""),
            "alert_color": "high" if float(row.get("sc") or 0) >= 8 else "orange",
            "score": row.get("sc", 0),
            "url": row.get("u", ""),
            "target_url": "#breadth?alert=alert",
        }
        for row in raw_records
        if int(row.get("lv") or 0) >= 3
        and not int(row.get("dp") or 0)
        and int(row.get("cp") if row.get("cp") is not None else 0) != 1
    ]
    alerts.sort(key=lambda row: row.get("published_at", ""), reverse=True)

    payload = {
        "source": "breadth-alert-level-3",
        "generated_at": generated_at,
        "total": len(alerts),
        "items": alerts,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(alerts)} alerts to {output}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
DEFAULT_XMIND = ROOT / "行业图景" / "行业图景.xmind"
if not DEFAULT_XMIND.exists():
    DEFAULT_XMIND = PROJECT_ROOT / "行业图景" / "行业图景.xmind"
DEFAULT_OUTPUT = ROOT / "data" / "industry_map.json"


def normalize_topic(topic: dict[str, Any], path: list[str] | None = None, depth: int = 0) -> dict[str, Any]:
    title = str(topic.get("title") or "未命名节点").strip()
    current_path = [*(path or []), title]
    children = topic.get("children", {}).get("attached", [])
    return {
        "id": str(topic.get("id") or ""),
        "title": title,
        "depth": depth,
        "path": current_path,
        "children": [normalize_topic(child, current_path, depth + 1) for child in children],
        "coverage": {"intel": False, "special_issue": False, "dashboard": False},
        "links": {"intel": None, "special_issue": None, "dashboard": None},
    }


def count_nodes(node: dict[str, Any]) -> int:
    return 1 + sum(count_nodes(child) for child in node.get("children", []))


def max_depth(node: dict[str, Any]) -> int:
    children = node.get("children", [])
    if not children:
        return int(node.get("depth", 0))
    return max(max_depth(child) for child in children)


def parse_xmind(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("content.json")
    sheets = json.loads(raw.decode("utf-8"))
    if not sheets:
        raise ValueError("XMind content.json has no sheets")
    parsed_sheets = []
    for sheet in sheets:
        root_topic = sheet.get("rootTopic") or {}
        root = normalize_topic(root_topic)
        parsed_sheets.append({
            "id": str(sheet.get("id") or root.get("id") or root.get("title")),
            "title": str(sheet.get("title") or root.get("title") or "未命名sheet"),
            "root": root,
            "node_count": count_nodes(root),
            "max_depth": max_depth(root),
        })
    return {
        "source": str(path),
        "sheets": parsed_sheets,
        "sheet_count": len(parsed_sheets),
        "total_node_count": sum(item["node_count"] for item in parsed_sheets),
        "max_depth": max((item["max_depth"] for item in parsed_sheets), default=0),
    }

def main() -> None:
    data = parse_xmind(DEFAULT_XMIND)
    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {DEFAULT_OUTPUT}")
    print(f"sheet_count={data['sheet_count']} total_nodes={data['total_node_count']} max_depth={data['max_depth']}")
    for sheet in data['sheets']:
        print(f"- {sheet['title']} nodes={sheet['node_count']} max_depth={sheet['max_depth']}")


if __name__ == "__main__":
    main()

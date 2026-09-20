#!/usr/bin/env python3
"""从 data/industry-map-leaves.txt 生成三份分类产物：

1. data/industry_map.json        —— 行业图景树（/api/industry-map 与门户图谱页使用）
2. data/category-taxonomy.json   —— 扁平叶子分类表（上传资料 AI/人工分类使用）
3. data/taxonomy-manifest.json   —— 分类清单（数量校验 + 版本号）

叶子清单每行一条完整路径；路径中允许出现"复合标题"（标题本身含 "/"，
如 乙烯/丙烯/丁二烯、燃料转化（热/电）），由 COMPOSITE_PATH_TITLES 保证不被拆开。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEAVES_PATH = ROOT / "data" / "industry-map-leaves.txt"
RESULT_LABELS = ("不相关", "未分类")

# 标题本身含 "/" 的复合节点（与 backend/app/services/upload_ingestion.py 保持一致）
COMPOSITE_PATH_TITLES = (
    "乙烯/丙烯/丁二烯",
    "苯/甲苯/二甲苯",
    "水/油储热",
    "介电/导电材料",
    "导热/耐热材料",
    "燃料转化（热/电）",
    "隔离材料（膜材料/密封材料）",
    "直接电加热（电阻/电弧加热）",
)


def split_path(line: str) -> list[str]:
    parts = line.split("/")
    merged: list[str] = []
    i = 0
    while i < len(parts):
        three = "/".join(parts[i : i + 3])
        two = "/".join(parts[i : i + 2])
        if len(parts) - i >= 3 and three in COMPOSITE_PATH_TITLES:
            merged.append(three)
            i += 3
        elif len(parts) - i >= 2 and two in COMPOSITE_PATH_TITLES:
            merged.append(two)
            i += 2
        else:
            merged.append(parts[i])
            i += 1
    return merged


def node_id(path: list[str]) -> str:
    return "ind_" + hashlib.md5("/".join(path).encode("utf-8")).hexdigest()[:16]


def insert(root: dict, parts: list[str]) -> None:
    current = root
    for depth, title in enumerate(parts[1:], start=1):  # parts[0] 是 sheet 根
        children = current.setdefault("children", [])
        node = next((c for c in children if c["title"] == title), None)
        if node is None:
            path = parts[: depth + 1]
            node = {"id": node_id(path), "title": title, "depth": depth, "path": path}
            children.append(node)
        node["path"] = parts[: depth + 1]
        current = node


def finalize(node: dict, sheet_title: str) -> dict:
    path = node["path"]
    out = {
        "id": node["id"],
        "title": node["title"],
        "depth": node["depth"],
        "path": path,
    }
    children = node.get("children")
    if children:
        out["children"] = [finalize(c, sheet_title) for c in children]
    return out


def count(node: dict) -> int:
    return 1 + sum(count(c) for c in node.get("children", []))


def max_depth(node: dict) -> int:
    children = node.get("children", [])
    return max((max_depth(c) for c in children), default=node["depth"])


def main() -> int:
    leaves: list[list[str]] = []
    seen: set[str] = set()
    for raw in LEAVES_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = split_path(line)
        if len(parts) < 2:
            print(f"ERROR: 叶子至少要有根+一级节点: {line}", file=sys.stderr)
            return 1
        key = "/".join(parts)
        if key in seen:
            print(f"ERROR: 重复叶子: {key}", file=sys.stderr)
            return 1
        seen.add(key)
        leaves.append(parts)

    # 保持叶子清单中的出现顺序（零碳产业 → AI与智能科技 → 通用技术）
    roots = list(dict.fromkeys(parts[0] for parts in leaves))
    sheets = []
    for root_title in roots:
        root = {"id": node_id([root_title]), "title": root_title, "depth": 0, "path": [root_title]}
        for parts in leaves:
            if parts[0] == root_title:
                insert(root, parts)
        sheets.append(
            {
                "id": node_id([root_title]),
                "title": root_title,
                "root": finalize(root, root_title),
            }
        )

    total = sum(count(s["root"]) for s in sheets)
    depth = max(max_depth(s["root"]) for s in sheets)
    industry_map = {
        "source": "data/industry-map-leaves.txt（2026-09-20 版，本仓库维护）",
        "sheets": sheets,
        "sheet_count": len(sheets),
        "total_node_count": total,
        "max_depth": depth,
    }
    (ROOT / "data" / "industry_map.json").write_text(
        json.dumps(industry_map, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    categories = ["/".join(parts) for parts in leaves] + list(RESULT_LABELS)
    (ROOT / "data" / "category-taxonomy.json").write_text(
        json.dumps({"categories": categories}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    version = hashlib.sha256(
        json.dumps(categories, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    manifest = {
        "taxonomy_id": "techdb-industry-map",
        "taxonomy_version": version,
        "source_file": "category-taxonomy.json",
        "leaf_source": "industry-map-leaves.txt",
        "synced_at": "2026-09-20",
        "output_count": len(categories),
        "business_category_count": len(leaves),
        "result_labels": list(RESULT_LABELS),
        "note": "行业图景 2026-09-20 版：本仓库本地维护，与 data/industry_map.json 同源；breadth_data 挂载仅作回退。",
    }
    (ROOT / "data" / "taxonomy-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    print(f"leaves={len(leaves)} categories={len(categories)} nodes={total} max_depth={depth}")
    print(f"version={version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

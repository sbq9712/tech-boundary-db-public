#!/usr/bin/env python3
"""
Import taxonomy tree from industry_map.json into industry_nodes table.

Builds the full hierarchy (all levels, not just leaves) with parent_id links.
Idempotent: safe to re-run, upserts by stable id.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# When run inside the api container, these resolve to the app package
try:
    from app.db.session import SessionLocal
    from app.models.knowledge_node import IndustryNode
    HAS_DB = True
except ImportError:
    HAS_DB = False

# Try multiple paths: local dev, inside api container, etc.
_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "data" / "industry_map.json",  # dev: project_root/data/
    Path("/app/data/industry_map.json"),     # container: if data dir mounted
    Path("/data/industry_map.json"),         # container: if data mounted at /data
]
DATA_PATH = next((p for p in _CANDIDATES if p.exists()), None)
if DATA_PATH is None:
    # fallback for error message
    DATA_PATH = _CANDIDATES[0]


def _make_id(path_parts: list[str]) -> str:
    """Stable id from path: md5 hash of full path, truncated."""
    raw = "/".join(path_parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
    return f"ind_{h}"


def _flatten_tree(node: dict, path: list[str] | None = None, depth: int = 0):
    """Yield (id, name, parent_id, path, depth) for every node in tree."""
    path = path or []
    title = node.get("title", "").strip()
    current_path = [*path, title]
    node_id = _make_id(current_path)
    parent_id = _make_id(path) if path else None

    yield {
        "id": node_id,
        "name": title,
        "parent_id": parent_id,
        "path": "/".join(current_path),
        "depth": depth,
    }

    for child in node.get("children", []):
        yield from _flatten_tree(child, current_path, depth + 1)


def run():
    if not DATA_PATH.exists():
        print(f"ERROR: {DATA_PATH} not found", file=sys.stderr)
        return 1

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    sheets = data.get("sheets", [])
    if not sheets:
        print("ERROR: no sheets in industry_map.json", file=sys.stderr)
        return 1

    all_nodes: list[dict] = []
    for sheet in sheets:
        root = sheet.get("root") or {}
        sheet_id = sheet.get("id", "")

        # Sheet root is a top-level node (e.g. "零碳产业")
        for node_data in _flatten_tree(root):
            node_data["sheet_id"] = sheet_id
            node_data["sheet_title"] = sheet.get("title", "")
            all_nodes.append(node_data)

    # Deduplicate by id (different sheets might have same-named nodes)
    seen_ids: dict[str, dict] = {}
    for nd in all_nodes:
        if nd["id"] not in seen_ids:
            seen_ids[nd["id"]] = nd
    unique_nodes = list(seen_ids.values())

    if not HAS_DB:
        # Dry run: print summary
        leaves = [n for n in unique_nodes if not any(
            m["parent_id"] == n["id"] for m in unique_nodes
        )]
        print(f"[DRY RUN] Would import {len(unique_nodes)} nodes ({len(leaves)} leaves)")
        for n in unique_nodes[:5]:
            print(f"  {n['id']} | depth={n['depth']} | {n['name']} | parent={n['parent_id']}")
        return 0

    db = SessionLocal()
    try:
        imported = 0
        updated = 0
        # Sort by depth to ensure parents exist before children
        unique_nodes.sort(key=lambda x: x["depth"])

        for nd in unique_nodes:
            existing = db.query(IndustryNode).filter(
                IndustryNode.id == nd["id"]
            ).first()

            if existing:
                existing.name = nd["name"]
                existing.parent_id = nd["parent_id"]
                existing.description = nd["path"]
                updated += 1
            else:
                node = IndustryNode(
                    id=nd["id"],
                    name=nd["name"],
                    parent_id=nd["parent_id"],
                    node_type="category" if nd["depth"] < 3 else "leaf",
                    description=nd["path"],
                    aliases=[],
                    status="active",
                )
                db.add(node)
                imported += 1

        db.commit()
        print(f"Done: {imported} imported, {updated} updated, {len(unique_nodes)} total")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3
"""Publish BoundaryDB-local QA rebuild assets into canonical-qa.

This script no longer reads any tech-db checkout. Base vector/BM25/lite assets
come from scripts/rebuild_qa_base_index.py output, and the graph asset comes
from BoundaryDB's graph-live publication.

Typical flow:
  pipeline/.venv/bin/python scripts/rebuild_qa_base_index.py embed
  pipeline/.venv/bin/python scripts/rebuild_qa_base_index.py assemble
  python3 scripts/refresh_qa_assets.py

The expensive rebuild and the publish/copy step remain separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "services" / "canonical-qa"
MANIFEST = QA / "qa-backend" / "qa-assets-manifest.json"
DEFAULT_SOURCE = ROOT / "runtime" / "qa-base-rebuild"
DEFAULT_GRAPH = QA / "graph-live" / "graph-export.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    ap.add_argument("--source-version", default="")
    args = ap.parse_args()

    source = args.source.resolve()
    graph = args.graph.resolve()
    lightrag = QA / "data" / "lightrag"
    processed = QA / "data" / "processed"
    lightrag.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    pairs = [
        (source / "vector_index_v2.pkl", lightrag / "vector_index_v2.pkl"),
        (source / "bm25_index.pkl", lightrag / "bm25_index.pkl"),
        (source / "jieba_custom_dict.txt", lightrag / "jieba_custom_dict.txt"),
        (source / "all-records-lite.json", processed / "all-records-lite.json"),
        (graph, lightrag / "graph-export.json"),
    ]
    for src, dst in pairs:
        if not src.is_file():
            raise SystemExit(f"[FATAL] 缺少 BoundaryDB QA 资产: {src}")
        shutil.copy2(src, dst)
        print(f"copied {src.name} -> {dst.relative_to(ROOT)}")

    total = len(json.loads((processed / "all-records-lite.json").read_text("utf-8")))
    with (lightrag / "vector_index_v2.pkl").open("rb") as f:
        vector_meta = pickle.load(f)["meta"]
    with (lightrag / "bm25_index.pkl").open("rb") as f:
        bm25_meta = pickle.load(f)["meta"]
    if len(vector_meta) != len(bm25_meta) or len(vector_meta) != total:
        raise SystemExit("[FATAL] QA 基础索引、BM25、lite 数量不一致")

    manifest = json.loads(MANIFEST.read_text("utf-8"))
    rebuild_manifest = source / "manifest.json"
    source_version = args.source_version
    if not source_version and rebuild_manifest.is_file():
        source_version = str(json.loads(rebuild_manifest.read_text("utf-8")).get("data_version_hint") or "")
    manifest["source_kind"] = "tech-boundary-db"
    manifest["source_version"] = source_version or "boundary-local-rebuild"
    # 兼容旧读取器；运行逻辑不得将其解释为外部仓库依赖。
    manifest["upstream_commit"] = manifest["source_version"]
    manifest["expected_total_records"] = total
    manifest["expected_indexed_records"] = len(vector_meta)

    for rel in (
        "data/lightrag/vector_index_v2.pkl",
        "data/lightrag/bm25_index.pkl",
        "data/lightrag/jieba_custom_dict.txt",
        "data/lightrag/graph-export.json",
        "data/processed/all-records-lite.json",
    ):
        p = QA / rel
        manifest["files"][rel] = {"bytes": p.stat().st_size, "sha256": sha256(p)}

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest updated: source={manifest['source_version']} total={total} indexed={len(vector_meta)}")


if __name__ == "__main__":
    main()

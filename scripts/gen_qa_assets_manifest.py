#!/usr/bin/env python3
"""基础索引重建落地第 4 步：重新生成 qa-assets-manifest.json。

check_assets.py（镜像构建期 HEALTHCHECK 前置校验）按本清单逐文件校验
字节数 + SHA-256，并断言 记录总数/索引条数/向量维度 与预期一致。基础索引
离线重建产出新资产后，清单必须同步重算，否则镜像构建即失败。

模型与图谱资产未变（bge-m3-model/*、graph-export.json），其条目从现有
清单原样继承；重建产物（向量/BM25/jieba 词典/lite）按磁盘实文件重算。
用法：
  python scripts/gen_qa_assets_manifest.py \
      --rebuild-dir runtime/qa-base-rebuild \
      --service-dir services/canonical-qa
（--apply 才写回 qa-assets-manifest.json；缺省仅预览 diff）
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REBUILT_FILES = {
    "data/lightrag/vector_index_v2.pkl": "vector_index_v2.pkl",
    "data/lightrag/bm25_index.pkl": "bm25_index.pkl",
    "data/lightrag/jieba_custom_dict.txt": "jieba_custom_dict.txt",
    "data/processed/all-records-lite.json": "all-records-lite.json",
}
CARRIED_FILES = [
    "bge-m3-model/pytorch_model.bin",
    "bge-m3-model/config.json",
    "bge-m3-model/tokenizer.json",
    "data/lightrag/graph-export.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild-dir", type=Path, required=True)
    ap.add_argument("--service-dir", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="写回 qa-assets-manifest.json")
    args = ap.parse_args()

    manifest_path = args.service_dir / "qa-backend" / "qa-assets-manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))

    lite_path = args.rebuild_dir / "all-records-lite.json"
    records = json.loads(lite_path.read_text("utf-8"))

    import pickle

    with (args.rebuild_dir / "vector_index_v2.pkl").open("rb") as f:
        vector = pickle.load(f)
    with (args.rebuild_dir / "bm25_index.pkl").open("rb") as f:
        bm25 = pickle.load(f)

    manifest["expected_total_records"] = len(records)
    manifest["expected_indexed_records"] = len(vector["meta"])
    if len(bm25["meta"]) != len(vector["meta"]):
        raise SystemExit(f"向量/BM25 条数不一致: {len(vector['meta'])} != {len(bm25['meta'])}")
    manifest["expected_embedding_dim"] = int(vector["dim"])

    changed = []
    for rel, fname in REBUILT_FILES.items():
        path = args.rebuild_dir / fname
        entry = {"bytes": path.stat().st_size, "sha256": sha256(path)}
        if manifest["files"].get(rel) != entry:
            changed.append(rel)
        manifest["files"][rel] = entry
    for rel in CARRIED_FILES:
        if rel not in manifest["files"]:
            raise SystemExit(f"现有清单缺少应继承的条目：{rel}")

    preview = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    print(json.dumps({k: manifest[k] for k in manifest if k != "files"}, ensure_ascii=False, indent=2))
    print(f"重算条目：{changed or '无变化'}")
    if args.apply:
        manifest_path.write_text(preview, "utf-8")
        print(f"已写回 {manifest_path}")
    else:
        print("（预览模式，未写回；加 --apply 生效）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

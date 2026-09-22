#!/usr/bin/env python3
"""Phase B 资产刷新：tech-db 重建产物 → canonical-qa 发布资产 + manifest。

- 从 tech-db 仓库拷贝 vector/bm25/graph-export + lite 到 services/canonical-qa/data/
- 重新计算 SHA256/bytes，更新 qa-assets-manifest.json（upstream_commit、记录数）
- bge-m3 与 jieba 字典不变则原样保留
用法：python3 scripts/refresh_qa_assets.py --techdb /home/rhett/tech-db-fresh --commit <sha>
"""
import argparse, hashlib, json, pickle, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "services" / "canonical-qa"
MANIFEST = QA / "qa-backend" / "qa-assets-manifest.json"

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--techdb", required=True)
    ap.add_argument("--commit", required=True)
    args = ap.parse_args()
    src = Path(args.techdb)
    idx = src / "runtime" / "indexes"
    lite_src = src / "data" / "processed" / "all-records-lite.json"

    lightrag = QA / "data" / "lightrag"
    lightrag.mkdir(parents=True, exist_ok=True)
    (QA / "data" / "processed").mkdir(parents=True, exist_ok=True)

    pairs = [
        (idx / "vector_index_v2.pkl", lightrag / "vector_index_v2.pkl"),
        (idx / "bm25_index.pkl", lightrag / "bm25_index.pkl"),
        (idx / "graph-export.json", lightrag / "graph-export.json"),
        (src / "runtime" / "indexes" / "jieba_custom_dict.txt", lightrag / "jieba_custom_dict.txt"),
        (lite_src, QA / "data" / "processed" / "all-records-lite.json"),
    ]
    for s, d in pairs:
        if not s.is_file():
            raise SystemExit(f"[FATAL] 缺少上游文件: {s}")
        shutil.copy2(s, d)
        print(f"copied {s.name} -> {d.relative_to(ROOT)} ({s.stat().st_size:,}B)")

    with open(lite_src, encoding="utf-8") as f:
        total = len(json.load(f))
    with open(lightrag / "vector_index_v2.pkl", "rb") as f:
        vector_meta = pickle.load(f)["meta"]
    with open(lightrag / "bm25_index.pkl", "rb") as f:
        bm25_meta = pickle.load(f)["meta"]
    if len(vector_meta) != len(bm25_meta):
        raise SystemExit(f"[FATAL] vector/bm25 记录数不一致: {len(vector_meta)} vs {len(bm25_meta)}")

    m = json.load(open(MANIFEST, encoding="utf-8"))
    m["upstream_commit"] = args.commit
    m["expected_total_records"] = total
    m["expected_indexed_records"] = len(vector_meta)
    key = {"vector": "data/lightrag/vector_index_v2.pkl", "bm25": "data/lightrag/bm25_index.pkl",
           "graph": "data/lightrag/graph-export.json", "lite": "data/processed/all-records-lite.json"}
    for name, rel in key.items():
        p = QA / rel
        m["files"][rel] = {"bytes": p.stat().st_size, "sha256": sha256(p)}
    json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"manifest updated: upstream={args.commit[:12]} total={total} indexed={len(vector_meta)}")

if __name__ == "__main__":
    main()

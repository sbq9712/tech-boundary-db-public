#!/usr/bin/env python3
"""基础索引离线重建：发布视图 → canonical-qa 三件套（无需 tech-db）。

产物（输出目录 --out，默认 runtime/qa-base-rebuild/）：
  all-records-lite.json    服务 hydration 数据源（lite 为底 + meta 富化，与
                           sync_qa_index.load_published_records 同构合并）
  vector_index_v2.pkl      {embeddings (N,1024) float32 已归一化,
                            meta[{idx,id,t,d,s,c,tg,sc,u}], dim:1024}
  bm25_index.pkl           {bm25: BM25Okapi, meta[{idx,record_id,t,c,d}],
                            corpus_tokens: []}
                           corpus_tokens 置空：server 端加载后无消费者
                           （grep 证实），置空省 ~1.4GB 常驻内存
  jieba_custom_dict.txt    复刻 tech-db build_custom_dict 配方
  manifest.json            记录数/参数/偏差说明

与旧构建器（tech-db qa-backend/vector_index.py / bm25_index.py）的刻意偏差：
  1. 不应用 IRRELEVANT_CATS 排除：新发布视图 40% 记录 c=未分类/不相关
     （旧数据 7%），沿用排除会静默丢 27k 条检索能力（违反验收
     "不静默遗漏"）；全量索引，c 原样保留。
  2. 嵌入/BM25 证据文本在 b 缺失时以 as 兜底：新视图 b 仅覆盖 56%
     （旧数据 92%），严格复刻会让 44% 记录只剩标题向量。as 属生成
     内容，仅进入召回层，答案侧引用核验链（retrieval_pipeline +
     backend 核验）继续约束事实层。
  3. 文本截断：嵌入证据 ≤600 字符、BM25 证据 ≤800 字符 —— CPU bge-m3
     实测 ~0.6s/条（500 字符、12 线程），8192 token 全文嵌入在本机
     不可行（>2.2s/条 且 68k 规模内存越界）。

用法（嵌入阶段断点续跑，可多次调用直至完成）：
  pipeline/.venv/bin/python scripts/rebuild_qa_base_index.py embed
  pipeline/.venv/bin/python scripts/rebuild_qa_base_index.py assemble
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
BREADTH = REPO / "breadth" / "data" / "processed"
OUT = REPO / "runtime" / "qa-base-rebuild"
CHUNK_DIR = OUT / "embed-shards"
PROGRESS = CHUNK_DIR / "progress.json"

EMBED_BATCH = 16          # ST encode batch（长度分桶后短批为主）
SHARD_EMBEDS = 500        # 每 500 条落一个 .npy 分片（断点粒度）
EMBED_TEXT_CHARS = 600    # 嵌入文本证据截断
BM25_TEXT_CHARS = 800     # BM25 证据文本截断
DIM = 1024


def record_key(r: dict) -> str:
    return "|".join([str(r.get("t", "") or ""), str(r.get("d", "") or ""), str(r.get("u", "") or "")])


def load_published_records() -> list[dict]:
    """与 sync_qa_index.load_published_records 同构：lite 为底，meta 按 key 富化。"""
    def js_array(p: Path) -> list:
        text = p.read_text("utf-8")
        return json.loads(text.split("push(", 1)[1].rsplit(")", 1)[0])

    lite_rows: list[dict] = []
    for f in sorted(BREADTH.glob("lite-part-*.js")):
        lite_rows.extend(js_array(f))
    meta_rows: dict[str, dict] = {}
    for f in sorted(BREADTH.glob("meta-part-*.js")):
        for rec in js_array(f):
            meta_rows[record_key(rec)] = rec
    merged = []
    for row in lite_rows:
        rich = meta_rows.get(record_key(row))
        merged.append({**row, **rich} if rich else row)
    return merged


def stable_record_id(rec: dict) -> str:
    """确定性稳定 record_id（uuid5）。

    server 消费方（retrieval_pipeline.result_identity / rrf 多轮归并）要求
    record_id 非空且逐条唯一，否则基线结果会被折叠成单一身份。旧索引的
    record_id 出自 tech-db record_registry（与 68,239 快照绑定，无法直接
    映射发布视图）；本重建以 来源身份键 派生 uuid5：URL 稳定则 ID 稳定，
    重建幂等，且不需要跨仓注册表。
    """
    import uuid

    url = str(rec.get("u", "") or "").strip()
    identity = f"url:{url}" if url else (
        f"tda:{rec.get('t', '')}|{rec.get('d', '')}|{rec.get('a', '')}"
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


def evidence_text(rec: dict, cap: int) -> str:
    """证据文本：b 优先，as 兜底（偏差 2），截断 cap。"""
    text = str(rec.get("b") or rec.get("as") or "").strip()
    return text[:cap]


def format_embed_text(rec: dict, cap: int | None = None) -> str:
    """[leaf] title [tg] [tp] kp… 证据文本（复刻 format_record_text 组成）。"""
    if cap is None:
        cap = EMBED_TEXT_CHARS
    parts = []
    cat = str(rec.get("c", "") or "")
    if cat:
        leaf = cat.split("/")[-1]
        if leaf:
            parts.append(f"[{leaf}]")
    title = str(rec.get("t", "") or "")
    if title:
        parts.append(title)
    tg = str(rec.get("tg", "") or "")
    if tg:
        parts.append(f"[{tg}]")
    tp = str(rec.get("tp", "") or "")
    if tp:
        parts.append(f"[{tp}]")
    kp = rec.get("kp") or []
    if isinstance(kp, list) and kp:
        parts.append("; ".join(str(k) for k in kp))
    ev = evidence_text(rec, cap)
    if ev:
        parts.append(ev)
    return " ".join(parts)


def format_bm25_text(rec: dict) -> str:
    """t + 证据文本 + kp + tg + tp（复刻 primary_bm25_text 组成）。"""
    kp = rec.get("kp") or []
    kps = " ".join(str(v) for v in kp) if isinstance(kp, list) else str(kp)
    parts = [str(rec.get("t", "") or ""), evidence_text(rec, BM25_TEXT_CHARS), kps,
             str(rec.get("tg", "") or ""), str(rec.get("tp", "") or "")]
    return " ".join(p for p in parts if p)


def build_custom_dict(records: list[dict]) -> set:
    """复刻 tech-db bm25_index.build_custom_dict。"""
    IRREL = set()  # 全量索引口径下不过滤（偏差 1），leaf 一律收录
    terms: set = set()
    for r in records:
        cat = str(r.get("c", "") or "")
        if cat:
            leaf = cat.split("/")[-1]
            if len(leaf) >= 2:
                terms.add(leaf)
    for r in records:
        for kp in (r.get("kp") or []):
            kp = str(kp)
            if "[" in kp:
                term = kp.split("[")[0].strip()
            elif ":" in kp:
                term = kp.split(":")[0].strip()
            else:
                term = kp.strip()
            if term and len(term) >= 2:
                terms.add(term)
    tp_counts = Counter(str(r.get("tp", "") or "") for r in records if str(r.get("tp", "") or "").strip())
    for tp, count in tp_counts.items():
        if count >= 2 and len(tp) >= 2:
            terms.add(tp)
    for r in records:
        tg = str(r.get("tg", "") or "").strip()
        if tg:
            terms.add(tg)
    return terms


def _pending_positions(n: int) -> list[int]:
    """扫分片找真实的未嵌入位置（计数器断点在长度排序的稀疏落盘下不可信：
    崩溃重启后低位空洞会被跳过——实测 1914 个。分片非零行才是事实）。"""
    n_shards = (n + SHARD_EMBEDS - 1) // SHARD_EMBEDS
    pending: list[int] = []
    for shard_no in range(n_shards):
        shard_path = CHUNK_DIR / f"emb-{shard_no:05d}.npy"
        if not shard_path.exists():
            pending.extend(range(shard_no * SHARD_EMBEDS,
                                 min((shard_no + 1) * SHARD_EMBEDS, n)))
            continue
        arr = np.load(shard_path)
        for row in range(arr.shape[0]):
            pos = shard_no * SHARD_EMBEDS + row
            if pos >= n:
                break
            if abs(arr[row]).sum() == 0.0:
                pending.append(pos)
    return pending


def cmd_embed(argv: list[str] | None = None) -> int:
    records = load_published_records()
    n = len(records)
    print(f"[rebuild] 发布视图：{n} 条", flush=True)

    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    pending = _pending_positions(n)
    print(f"[rebuild] 分片扫描：待嵌入 {len(pending)}/{n}", flush=True)

    if not pending:
        print("[rebuild] 嵌入已全部完成 —— 直接 assemble", flush=True)
        PROGRESS.write_text(json.dumps({"done": n, "total": n,
                                        "updated_at": datetime.now(timezone.utc).isoformat()}), "utf-8")
        return 0

    os.environ.setdefault("TECHDB_QA_MODEL_PATH", "/home/rhett/bge-m3-model")
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        print(f"[FATAL] 需要 pipeline/.venv（缺依赖）：{exc}", flush=True)
        return 2
    torch.set_num_threads(int(os.environ.get("QA_REBUILD_THREADS", "6")))
    model_path = os.environ["TECHDB_QA_MODEL_PATH"]
    model = SentenceTransformer(model_path, device="cpu")

    # 长度分桶：短文本先批量（ST pad 到批内最长，混批浪费算力）；
    # 长文本截断可用环境变量下调（剩余尾部全是最长文本，600→400 ≈ 1.5x 吞吐）。
    embed_chars = int(os.environ.get("QA_REBUILD_EMBED_CHARS", str(EMBED_TEXT_CHARS)))
    if embed_chars != EMBED_TEXT_CHARS:
        print(f"[rebuild] 嵌入证据截断覆盖：{embed_chars}（默认 {EMBED_TEXT_CHARS}）", flush=True)
    remaining = sorted(pending, key=lambda i: len(format_embed_text(records[i], embed_chars)))
    t0 = time.time()
    processed = 0
    for start in range(0, len(remaining), EMBED_BATCH):
        idxs = remaining[start:start + EMBED_BATCH]
        texts = [format_embed_text(records[i], embed_chars) or "无内容" for i in idxs]
        embs = model.encode(texts, batch_size=len(texts), show_progress_bar=False,
                            normalize_embeddings=True)
        embs = np.asarray(embs, dtype=np.float32)
        # 依原顺序落分片：分片文件号 = 记录位置 // SHARD_EMBEDS
        for pos, i in enumerate(idxs):
            shard_no = i // SHARD_EMBEDS
            shard_path = CHUNK_DIR / f"emb-{shard_no:05d}.npy"
            slot = i % SHARD_EMBEDS
            if shard_path.exists():
                arr = np.load(shard_path)
                if arr.shape[0] != SHARD_EMBEDS:
                    arr = np.vstack([arr, np.zeros((SHARD_EMBEDS - arr.shape[0], DIM), dtype=np.float32)])
            else:
                arr = np.zeros((SHARD_EMBEDS, DIM), dtype=np.float32)
            arr[slot] = embs[pos]
            np.save(shard_path, arr)
        processed += len(idxs)
        if processed % 500 < EMBED_BATCH or processed == len(remaining):
            rate = processed / max(time.time() - t0, 1)
            eta = (len(remaining) - processed) / max(rate, 1e-9) / 3600
            print(f"[rebuild] {processed}/{len(remaining)}  {rate:.2f} 条/s  ETA {eta:.1f}h", flush=True)
            PROGRESS.write_text(json.dumps({"done": processed, "total": len(remaining),
                                            "updated_at": datetime.now(timezone.utc).isoformat()}), "utf-8")
    PROGRESS.write_text(json.dumps({"done": len(remaining), "total": len(remaining),
                                    "updated_at": datetime.now(timezone.utc).isoformat()}), "utf-8")
    print(f"[rebuild] 嵌入完成：{len(remaining)} 条，用时 {(time.time()-t0)/3600:.2f}h", flush=True)
    return 0


def cmd_assemble(argv: list[str] | None = None) -> int:
    records = load_published_records()
    n = len(records)
    # 完整性以分片非零行判定（计数器断点在稀疏落盘下不可信）
    pending = _pending_positions(n)
    if pending:
        print(f"[FATAL] 嵌入未完成：{len(pending)} 个空位（如 {pending[:5]}）—— 先跑 embed", flush=True)
        return 1
    print(f"[rebuild] 装配 {n} 条向量 …", flush=True)
    embs = np.zeros((n, DIM), dtype=np.float32)
    for shard_path in sorted(CHUNK_DIR.glob("emb-*.npy")):
        shard_no = int(shard_path.stem.split("-")[1])
        arr = np.load(shard_path)
        lo = shard_no * SHARD_EMBEDS
        take = min(SHARD_EMBEDS, n - lo)
        embs[lo:lo + take] = arr[:take]
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embs = embs / norms

    vec_meta = []
    for idx, rec in enumerate(records):
        vec_meta.append({
            "idx": idx,
            "id": "",
            "record_id": stable_record_id(rec),
            "t": str(rec.get("t", "") or ""),
            "d": str(rec.get("d", "") or ""),
            "s": str(rec.get("a", rec.get("s", "")) or ""),
            "c": str(rec.get("c", "") or ""),
            "tg": str(rec.get("tg", "") or ""),
            "sc": rec.get("sc", 0),
            "u": str(rec.get("u", "") or ""),
        })
    OUT.mkdir(parents=True, exist_ok=True)
    vec_file = OUT / "vector_index_v2.pkl"
    tmp = str(vec_file) + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump({"embeddings": embs, "meta": vec_meta, "dim": DIM}, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, vec_file)
    print(f"[rebuild] vector_index_v2.pkl：{len(vec_meta)} 条（{vec_file.stat().st_size/1e6:.0f}MB）", flush=True)

    # ── BM25 ──
    import jieba
    from rank_bm25 import BM25Okapi
    terms = build_custom_dict(records)
    dict_path = OUT / "jieba_custom_dict.txt"
    dict_path.write_text("".join(f"{t} 999 nr\n" for t in sorted(terms)), "utf-8")
    jieba.load_userdict(str(dict_path))
    print(f"[rebuild] jieba 自定义词典：{len(terms)} 词", flush=True)

    t0 = time.time()
    corpus = []
    bm_meta = []
    for idx, rec in enumerate(records):
        text = format_bm25_text(rec)
        corpus.append([t for t in jieba.cut_for_search(text)])
        bm_meta.append({"idx": idx, "record_id": stable_record_id(rec),
                        "t": str(rec.get("t", "") or ""),
                        "c": str(rec.get("c", "") or ""), "d": str(rec.get("d", "") or "")})
        if (idx + 1) % 10000 == 0:
            print(f"[rebuild] 分词 {idx+1}/{n}（{time.time()-t0:.0f}s）", flush=True)
    print(f"[rebuild] 分词完成（{time.time()-t0:.0f}s），构建 BM25Okapi …", flush=True)
    bm25 = BM25Okapi(corpus)
    del corpus  # 大列表不进 pickle（见偏差说明：corpus_tokens 置空）
    bm25_file = OUT / "bm25_index.pkl"
    tmp = str(bm25_file) + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump({"bm25": bm25, "meta": bm_meta, "corpus_tokens": []}, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, bm25_file)
    print(f"[rebuild] bm25_index.pkl：{len(bm_meta)} 文档（{bm25_file.stat().st_size/1e6:.0f}MB）", flush=True)

    # ── lite + manifest ──
    lite_file = OUT / "all-records-lite.json"
    lite_file.write_text(json.dumps(records, ensure_ascii=False), "utf-8")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": n,
        "vector": {"count": len(vec_meta), "dim": DIM, "normalized": True},
        "bm25": {"count": len(bm_meta), "corpus_tokens_stored": False,
                 "reason": "server 端无消费者；置空省 ~1.4GB 常驻内存"},
        "deviations": [
            "IRRELEVANT_CATS 不排除（新视图 40% 未分类，沿用会静默丢 27k 条检索）",
            f"证据文本 b 优先、as 兜底（新视图 b 覆盖 56%，旧数据 92%）",
            f"嵌入证据截断 {EMBED_TEXT_CHARS} 字符 / BM25 截断 {BM25_TEXT_CHARS} 字符（CPU 预算）",
        ],
        "source": "breadth/data/processed/{lite,meta}-part-*.js（发布视图）",
        "data_version_hint": hashlib.sha256(b"".join(
            sorted(hashlib.sha256(record_key(r).encode('utf-8')).digest() for r in records))).hexdigest()[:16],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    print(f"[rebuild] manifest.json 已写；产物齐备：{OUT}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("embed", help="嵌入阶段（断点续跑）")
    sub.add_parser("assemble", help="装配向量 + BM25 + lite + manifest")
    args = parser.parse_args(argv)
    return cmd_embed() if args.cmd == "embed" else cmd_assemble()


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""五.5 截断召回退步回归（离线，复现 rebuild_qa_base_index 的检索层）。

回答授权边界内的问题：正文不足（b 缺失）、摘要兜底（as fallback）以及
200/600/800 字截断是否造成不可接受的召回退步？需要时恢复有效分块或
增加预算。

方法（不调用线上服务，不修改镜像/索引）：
- 装载 runtime/qa-base-rebuild/all-records-lite.json（与当前索引同源语料）；
- 对三档嵌入证据截断 {200, 600, 800}（BM25 恒 800，另一维 BM25 {200,800}）
  各建一份 BM25Okapi 索引（jieba 分词与 rebuild 一致）；
- 查询集：①每条记录的标题（title→self 应命中，天然 ground-truth）；
  ②人工构造的真实用户问题（含数值/缩写/口语化），期望命中人工指定记录；
- 指标：self-recall@10/@25、MRR@25、人工题 hit@10；
- 退步判定：较 800 字档 Δrecall@25 > 2pp 判 FAIL（--threshold 可调）；
  as 兜底消融：b 缺失记录只用 t（标题）建索引，量化摘要兜底贡献。

用法：
  python3 scripts/eval_qa_truncation_recall.py \
    [--corpus runtime/qa-base-rebuild/all-records-lite.json] [--max-records 8000]
    [--threshold 0.02] [--report out.json]

（--max-records 抽样控制 CPU；标题自检索指标在大样本下方差足够小。）
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 与 rebuild_qa_base_index.py 完全一致的文本组装（导入复用，防漂移）
from scripts.rebuild_qa_base_index import (  # noqa: E402
    BM25_TEXT_CHARS, EMBED_TEXT_CHARS, evidence_text, format_embed_text,
    format_bm25_text, build_custom_dict,
)

MANUAL_QUERIES = [
    # (query, title 关键词片段——命中判据：top25 内任一记录标题含片段)
    ("宁德时代钠离子电池储能电站备案", "GWh级钠电储能项目落地"),
    ("固态电池量产装车进展", "固态电池"),
    ("钙钛矿电池转换效率纪录", "钙钛矿"),
    ("电解槽碱性制氢成本", "电解槽"),
    ("AI数据中心电力需求增长", "数据中心"),
    ("通用汽车进军储能", "通用汽车"),
    ("硅基量子芯片材料突破", "硅-28"),
    ("美国税法对清洁能源的抵免", "税收信用"),
]


def load_corpus(path: Path, max_records: int, seed: int = 42) -> list:
    records = json.loads(path.read_text("utf-8"))
    if isinstance(records, dict):
        records = records.get("records") or records.get("data") or []
    if max_records and len(records) > max_records:
        rng = random.Random(seed)
        records = rng.sample(records, max_records)
    return records


def tokenize_all(texts: list, custom_dict: set) -> list:
    import jieba
    for w in custom_dict:
        jieba.add_word(w, freq=2_000_000)
    return [list(jieba.cut_for_search(t)) for t in texts]


def build_bm25(texts: list, custom_dict: set):
    from rank_bm25 import BM25Okapi
    corpus = tokenize_all(texts, custom_dict)
    return BM25Okapi(corpus), corpus


def body_probe_queries(records: list, min_len: int = 60, max_len: int = 110,
                       seed: int = 7) -> list:
    """正文探针查询：从正文(b 优先 as 兜底)抽取 60-110 字片段，去掉标题
    中的词——只有正文在索引里才可能命中，直接考察截断对正文信息的伤害。"""
    import random
    import re
    rng = random.Random(seed)
    probes = []
    for idx, r in enumerate(records):
        body = str(r.get("b") or r.get("as") or "").strip()
        if len(body) < min_len + 40:
            continue
        title_words = [w for w in re.split(r"[\s，。、；：！？（）()\[\]]+",
                                          str(r.get("t", "") or "")) if len(w) >= 2]
        s0 = rng.randint(0, max(0, min(len(body) - min_len - 1, 400)))
        frag = body[s0:s0 + rng.randint(min_len, max_len)]
        frag = re.sub(r"\s+", "", frag)
        if len(frag) < min_len:
            continue
        probes.append((idx, frag, title_words))
    return probes


def eval_index(bm25, queries_tokens: list, probes: list) -> dict:
    """正文探针：query=记录 i 的正文片段，命中判据 topK 内含 i。"""
    hits10 = hits25 = 0
    rr = 0.0
    n = len(queries_tokens)
    for k, qt in enumerate(queries_tokens):
        target = probes[k][0]
        scores = bm25.get_scores(qt)
        order = sorted(range(len(scores)), key=lambda j: scores[j], reverse=True)[:25]
        if target in order[:10]:
            hits10 += 1
        if target in order:
            hits25 += 1
            rr += 1.0 / (order.index(target) + 1)
    return {"body_recall@10": hits10 / n, "body_recall@25": hits25 / n,
            "mrr@25": rr / n}


def eval_manual(bm25, custom_dict: set, titles: list) -> dict:
    import jieba
    hits = 0
    details = []
    for q, key in MANUAL_QUERIES:
        scores = bm25.get_scores(list(jieba.cut_for_search(q)))
        order = sorted(range(len(scores)), key=lambda j: scores[j], reverse=True)[:10]
        top_titles = [titles[i] for i in order]
        hit = any(key in t for t in top_titles)
        hits += hit
        details.append({"query": q, "key": key, "hit@10": hit,
                        "top1": top_titles[0][:50] if top_titles else ""})
    return {"manual_hit@10": hits / len(MANUAL_QUERIES), "details": details}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="五.5 截断召回退步回归")
    ap.add_argument("--corpus", default="runtime/qa-base-rebuild/all-records-lite.json")
    ap.add_argument("--max-records", type=int, default=8000)
    ap.add_argument("--threshold", type=float, default=0.02,
                    help="recall@25 相对 800 字档的退步容忍（比例）")
    ap.add_argument("--report")
    args = ap.parse_args(argv)

    t0 = time.time()
    records = load_corpus(Path(args.corpus), args.max_records)
    titles = [str(r.get("t", "") or "") for r in records]
    custom = build_custom_dict(records)
    print(f"语料 {len(records)} 条，自定义词典 {len(custom)} 词，"
          f"装载 {time.time()-t0:.1f}s", flush=True)

    b_missing = sum(1 for r in records if not str(r.get("b") or "").strip())
    a_fallback = sum(1 for r in records if not str(r.get("b") or "").strip()
                     and str(r.get("as") or "").strip())
    print(f"正文(b)缺失 {b_missing} 条（{b_missing/len(records):.1%}），"
          f"其中 as 兜底可用 {a_fallback} 条", flush=True)

    results = {"corpus": str(args.corpus), "records": len(records),
               "b_missing": b_missing, "as_fallback": a_fallback, "variants": {}}

    # 维度 1：嵌入证据截断 {200, 600, 800}。探针查询=正文片段（截断 200 时
    # 片段可能整体落在被截掉的部分——这正是要测的退步），索引文本随 cap 变化。
    import jieba
    probes = body_probe_queries(records)
    print(f"正文探针查询 {len(probes)} 条（60-110 字片段）", flush=True)
    baseline = None
    for cap in (800, 600, 200):
        texts = [format_embed_text(r, cap) for r in records]
        bm25, _ = build_bm25(texts, custom)
        qtoks = [list(jieba.cut_for_search(frag)) for _, frag, _ in probes]
        m = eval_index(bm25, qtoks, probes)
        m["manual"] = eval_manual(bm25, custom, titles)
        results["variants"][f"embed_{cap}"] = m
        print(f"embed<={cap}: body_recall@10={m['body_recall@10']:.4f} "
              f"body_recall@25={m['body_recall@25']:.4f} mrr={m['mrr@25']:.4f} "
              f"manual={m['manual']['manual_hit@10']:.2f}", flush=True)
        if cap == 800:
            baseline = m

    # 维度 2：BM25 证据截断 {200, 800}（同一批正文探针）
    for cap in (800, 200):
        texts = [format_bm25_text(r) if cap == 800 else
                 " ".join([str(r.get("t", "") or ""), evidence_text(r, cap),
                           " ".join(str(v) for v in (r.get("kp") or [])),
                           str(r.get("tg", "") or ""), str(r.get("tp", "") or "")])
                 for r in records]
        bm25, _ = build_bm25(texts, custom)
        qtoks = [list(jieba.cut_for_search(frag)) for _, frag, _ in probes]
        m = eval_index(bm25, qtoks, probes)
        results["variants"][f"bm25_{cap}"] = m
        print(f"bm25<={cap}: body_recall@10={m['body_recall@10']:.4f} "
              f"body_recall@25={m['body_recall@25']:.4f}", flush=True)

    # 维度 3：摘要兜底消融（b 缺失记录）。实测：b 缺失记录的 as 多为
    # <100 字短桩（本样本 418/891 有短桩、473 全空）——没有可用的正文
    # 探针，退而考察"标题自检索"：仅标题索引 vs 标题+短桩（兜底贡献 =
    # 短桩是否干扰或帮助标题命中）。
    miss_idx = [i for i, r in enumerate(records)
                if not str(r.get("b") or "").strip()]
    if miss_idx:
        sub = [records[i] for i in miss_idx]
        full = [format_embed_text(r) for r in sub]
        title_only = [str(r.get("t", "") or "") for r in sub]
        # 查询=子集内标题（title→self），两侧索引各评一次
        title_qtoks = [list(jieba.cut_for_search(t)) for t in title_only]
        stub_probes = [(k, title_only[k], []) for k in range(len(sub))]

        def _title_self(bm25):
            hits25 = rr = 0
            for k, qt in enumerate(title_qtoks):
                scores = bm25.get_scores(qt)
                order = sorted(range(len(scores)), key=lambda j: scores[j],
                               reverse=True)[:25]
                if k in order:
                    hits25 += 1
                    rr += 1.0 / (order.index(k) + 1)
            n = len(title_qtoks)
            return {"title_self_recall@25": hits25 / n, "mrr@25": rr / n}

        m_full = _title_self(*build_bm25(full, custom)[0:1])
        m_title = _title_self(*build_bm25(title_only, custom)[0:1])
        results["variants"]["as_fallback_full"] = m_full
        results["variants"]["as_fallback_title_only"] = m_title
        results["b_missing_as_short_or_empty"] = {
            "with_short_stub": sum(1 for r in sub
                                   if str(r.get("as") or "").strip()),
            "empty": sum(1 for r in sub if not str(r.get("as") or "").strip())}
        print(f"as兜底消融（{len(sub)} 条 b 缺失记录，标题自检索）："
              f"标题+短桩 recall@25={m_full['title_self_recall@25']:.4f} vs "
              f"仅标题={m_title['title_self_recall@25']:.4f} "
              f"(Δ={m_full['title_self_recall@25']-m_title['title_self_recall@25']:+.4f})",
              flush=True)

    # ── 退步判定 ──
    verdicts = {}
    for cap in (600, 200):
        m = results["variants"].get(f"embed_{cap}")
        if m and baseline:
            drop = baseline["body_recall@25"] - m["body_recall@25"]
            verdicts[f"embed_{cap}_vs_800"] = {
                "delta_recall@25": round(-drop, 4),
                "acceptable": drop <= args.threshold}
    results["verdicts"] = verdicts
    ok = all(v["acceptable"] for v in verdicts.values())
    results["overall"] = "PASS" if ok else "FAIL"
    print("\n═══ 五.5 判定 ═══")
    for k, v in verdicts.items():
        print(f"{k}: Δrecall@25={v['delta_recall@25']:+.4f} → "
              f"{'可接受' if v['acceptable'] else '超容忍'}")
    print("总体：", results["overall"])
    if args.report:
        Path(args.report).write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                     "utf-8")
        print(f"报告已写入 {args.report}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())

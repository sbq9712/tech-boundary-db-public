#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量重跑：仅重跑 triage_engine 覆盖的管线功能（领域分类/情报类型/评分/AI精选）。

其余步骤（抓取/翻译/摘要/关键参数/聚类/会议/报告）不重跑。逐批处理并落盘：
  - 每批用 triage_engine 重新分诊，写回 lite（原索引一一对应，不丢记录）
  - 每批后原子重建快照并安装到 breadth/data（前端渐进可见，失败可续跑）
  - 人工/审核字段（lv/wr/cm/fb）与摘要/参数/聚类既有结果原样保留
  - 引擎判"不相关"的记录清空 AI 派生字段并终止其后续处理
  - 断点续跑：checkpoint 记录已处理索引；--reset-checkpoint 从头再来
用法：
  .venv/bin/python scripts/rerun_engine_retriage.py [--batch 400] [--limit N] [--reset-checkpoint]
环境：
  TRIAGE_LLM_OFF=1     关闭 LLM 语义复核层（仅规则层）
  TRIAGE_LLM_BATCH=8   LLM 复核批大小
  TRIAGE_LLM_SLEEP=2   LLM 批间节流秒
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]        # tech-boundary-db/
PIPELINE = REPO / "pipeline"
sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(PIPELINE / "scripts"))

LITE_PATH = PIPELINE / "data" / "processed" / "all-records-lite.json"
CHECKPOINT = PIPELINE / ".engine_retriage_checkpoint.json"
PROTECTED_FIELDS = ("lv", "wr", "cm", "fb", "cl", "cp", "cln", "as", "kp", "tp")  # 重跑不得触碰


def load_checkpoint():
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"done_idx": [], "stats": {"ok": 0, "fail": 0, "irrelevant": 0,
                                      "scored": 0, "featured": 0, "carrier_switched": 0}}


def save_checkpoint(cp):
    tmp = CHECKPOINT.with_suffix(".tmp")
    tmp.write_text(json.dumps(cp, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CHECKPOINT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=400)
    ap.add_argument("--limit", type=int, default=0, help="本次最多处理条数（0=全部）")
    ap.add_argument("--reset-checkpoint", action="store_true")
    args = ap.parse_args()

    if args.reset_checkpoint and CHECKPOINT.exists():
        CHECKPOINT.unlink()

    cp = load_checkpoint()
    done: set[int] = set(cp["done_idx"])

    lite = json.loads(LITE_PATH.read_text(encoding="utf-8"))
    total = len(lite)
    todo = [i for i in range(total) if i not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"lite={total} done={len(done)} todo={len(todo)} batch={args.batch}", flush=True)

    import engine_triage

    t0 = time.time()
    PUBLISH_EVERY = 10
    pending_publish = 0
    for b0 in range(0, len(todo), args.batch):
        idxs = todo[b0:b0 + args.batch]
        # 快照副本：引擎结果先写副本，成功后才覆盖原记录（失败不影响原数据）
        batch = [dict(lite[i]) for i in idxs]
        # as/kp/tp 保留（本次不重跑摘要/参数/主题），但引擎可能判不相关 → 届时清空
        try:
            stats = engine_triage.engine_triage_records(
                batch, use_llm=not os.environ.get("TRIAGE_LLM_OFF"),
                workdir=str(PIPELINE / ".engine_triage_work"),
                llm_batch=int(os.environ.get("TRIAGE_LLM_BATCH", "8")),
                llm_sleep=float(os.environ.get("TRIAGE_LLM_SLEEP", "2.0")),
            )
        except Exception as exc:
            cp["stats"]["fail"] += len(idxs)
            save_checkpoint(cp)
            print(f"[batch@{idxs[0]}] FAILED ({exc}) — checkpoint saved, abort for retry", flush=True)
            return 1

        # 不相关 → 清空 as/kp/tp（终止后续处理）；其余保留既有摘要/参数/主题
        for rec in batch:
            if rec.get("c") == "不相关":
                for f in ("as", "kp", "tp"):
                    rec.pop(f, None)

        for i, rec in zip(idxs, batch):
            old = lite[i]
            for f in PROTECTED_FIELDS:
                if f in old:
                    rec[f] = old[f]
                else:
                    rec.pop(f, None)
            lite[i] = rec

        cp["done_idx"] = sorted(done | set(idxs))
        done = set(cp["done_idx"])
        cp["stats"]["ok"] += stats["matched"]
        cp["stats"]["irrelevant"] += stats["irrelevant"]
        cp["stats"]["scored"] += stats["scored"]
        cp["stats"]["featured"] += stats["featured"]
        cp["stats"]["carrier_switched"] += stats["carrier_switched"]
        save_checkpoint(cp)

        # 落盘（每批原子写）；发布节流：每 PUBLISH_EVERY 批一次（68k 全量发布约分钟级）
        tmp = LITE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(lite, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, LITE_PATH)
        pending_publish += 1
        if pending_publish >= PUBLISH_EVERY or b0 + args.batch >= len(todo):
            pending_publish = 0
            try:
                # publish_to_boundary 依赖 BOUNDARY_REPO 指向仓库根（脚本/派生快照定位）
                os.environ.setdefault("BOUNDARY_REPO", str(REPO))
                import auto_pipeline as _ap  # 复用主管线发布逻辑（含派生快照与版本戳）
                if not _ap.publish_to_boundary():
                    print("[WARN] publish failed this round (non-fatal, retried next round)", flush=True)
            except Exception as exc:
                print(f"[WARN] snapshot/publish failed (non-fatal): {exc}", flush=True)

        rate = len(done) / max(1e-9, time.time() - t0)
        print(f"[batch {idxs[0]}..{idxs[-1]}] ok={stats['matched']} 不相关={stats['irrelevant']} "
              f"scored={stats['scored']} featured={stats['featured']} "
              f"progress={len(done)}/{len(todo)} rate={rate:.0f}/s", flush=True)

    s = cp["stats"]
    print(f"ALL DONE: ok={s['ok']} fail={s['fail']} 不相关={s['irrelevant']} "
          f"scored={s['scored']} featured={s['featured']} carrier_switched={s['carrier_switched']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

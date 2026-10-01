#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量重跑：仅重跑 triage_engine 覆盖的管线功能（领域分类/情报类型/评分/AI精选）。

其余步骤（抓取/翻译/摘要/关键参数/聚类/会议/报告）不重跑。逐批处理并落盘：
  - 每批用 triage_engine 重新分诊，写回 lite（原索引一一对应，不丢记录）
  - 每批后原子重建快照并安装到 breadth/data（前端渐进可见，失败可续跑）
  - 人工/审核字段（lv/wr/cm/fb）与摘要/参数/聚类既有结果原样保留
  - 引擎判"不相关"的记录清空 AI 派生字段并终止其后续处理
  - 断点续跑：checkpoint 记录已处理记录（五.5，2026-10-01：改用稳定身份
    t|d|u 的 sha256，语料重排/增删后不再错位；读取旧位置式 checkpoint 时
    按当前语料一次性迁移）；--reset-checkpoint 从头再来
  - 五.5 顺序修复：先原子落盘数据、后推进断点——断点先于数据写时崩溃
    会把未持久化的批永久标成已处理（丢处理），数据先写则最坏只是重跑
用法：
  .venv/bin/python scripts/rerun_engine_retriage.py [--batch 400] [--limit N] [--reset-checkpoint]
环境：
  TRIAGE_LLM_OFF=1            关闭 LLM 语义复核层（仅规则层）
  TRIAGE_LLM_BATCH=8          LLM 复核批大小
  TRIAGE_LLM_SLEEP=1          LLM 批间节流秒
  TRIAGE_RETRIAGE_WORKERS=6   并发引擎子进程数（每批一个独立子进程，线程安全）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]        # tech-boundary-db/
PIPELINE = REPO / "pipeline"
sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(PIPELINE / "scripts"))

LITE_PATH = PIPELINE / "data" / "processed" / "all-records-lite.json"
CHECKPOINT = PIPELINE / ".engine_retriage_checkpoint.json"
PROTECTED_FIELDS = ("lv", "wr", "cm", "fb", "cl", "cp", "cln", "as", "kp", "tp")  # 重跑不得触碰


def acquire_run_lock():
    """七（2026-10-01）并发保护：同一 checkpoint 同时只允许一个重跑进程。
    两个进程会读同一断点、重复调用引擎并把彼此的写回/断点推进交错
    （checkpoint 非行锁，last-writer-wins 会造成丢处理）。flock 独占；
    拿不到锁立即退出（crontab 重叠触发场景）。"""
    import fcntl
    lock_path = CHECKPOINT.with_suffix(".lock")
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


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

    lock_fh = acquire_run_lock()
    if lock_fh is None:
        print("[FATAL] 另一个重跑进程正在运行（.engine_retriage_checkpoint.lock "
              "被占用）——并发重跑会交错写回/断点，拒绝启动", flush=True)
        return 1

    if args.reset_checkpoint and CHECKPOINT.exists():
        CHECKPOINT.unlink()

    cp = load_checkpoint()
    lite = json.loads(LITE_PATH.read_text(encoding="utf-8"))

    def rec_key(i: int) -> str:
        r = lite[i]
        return hashlib.sha256("|".join([str(r.get("t") or ""), str(r.get("d") or ""),
                                        str(r.get("u") or "")]).encode("utf-8")).hexdigest()

    if cp.get("done_idx") is not None and not cp.get("done_keys"):
        # 旧位置式 checkpoint 一次性迁移：按当前语料把位置翻译为稳定键。
        # 语料若已变化则无法可靠翻译——只迁移可校验范围并告警。
        legacy = set(cp["done_idx"])
        migrated = {rec_key(i) for i in legacy if 0 <= i < len(lite)}
        cp["done_keys"] = sorted(migrated)
        cp.pop("done_idx", None)
        save_checkpoint(cp)
        print(f"[migrate] 位置式 checkpoint → 稳定键 {len(migrated)} 条"
              f"（语料变化时旧位置可能错位，如需严格请 --reset-checkpoint）", flush=True)
    done: set[str] = set(cp.get("done_keys") or [])

    total = len(lite)
    todo = [i for i in range(total) if rec_key(i) not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"lite={total} done={len(done)} todo={len(todo)} batch={args.batch}", flush=True)

    import engine_triage

    workers = max(1, int(os.environ.get("TRIAGE_RETRIAGE_WORKERS", "6")))
    llm_batch = int(os.environ.get("TRIAGE_LLM_BATCH", "8"))
    llm_sleep = float(os.environ.get("TRIAGE_LLM_SLEEP", "1.0"))
    use_llm = not os.environ.get("TRIAGE_LLM_OFF")

    def triage_one(idxs):
        """工作线程：独立子进程跑引擎（线程安全——rows/out 均为调用级临时目录）。
        快照副本上改写，成功后由主线程按原索引写回（失败不影响原数据）。"""
        batch = [dict(lite[i]) for i in idxs]
        stats = engine_triage.engine_triage_records(
            batch, use_llm=use_llm,
            workdir=str(PIPELINE / ".engine_triage_work"),
            llm_batch=llm_batch, llm_sleep=llm_sleep,
        )
        # 不相关 → 清空 as/kp/tp（终止后续处理）；其余保留既有摘要/参数/主题
        for rec in batch:
            if rec.get("c") == "不相关":
                for f in ("as", "kp", "tp"):
                    rec.pop(f, None)
        return idxs, batch, stats

    batch_index_lists = [todo[b0:b0 + args.batch] for b0 in range(0, len(todo), args.batch)]

    t0 = time.time()
    PUBLISH_EVERY = 10
    pending_publish = 0
    # 引擎调用（LLM 受限型 I/O）并发执行；写回/断点/发布仍严格按批顺序在主线程执行
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for idxs, batch, stats in ex.map(triage_one, batch_index_lists):
            for i, rec in zip(idxs, batch):
                old = lite[i]
                if rec.get("c") == "不相关":
                    # 不相关 = 终态：引擎已清空全部 AI 派生字段，保护字段不得回填
                    lite[i] = rec
                    continue
                for f in PROTECTED_FIELDS:
                    if f in old:
                        rec[f] = old[f]
                    else:
                        rec.pop(f, None)
                lite[i] = rec

            # 五.5：先原子落盘数据、后推进断点——数据写失败时断点不动，
            # 重跑只重做本批；反之（旧行为）会把未持久化记录永久跳过。
            tmp = LITE_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(lite, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, LITE_PATH)

            fresh_keys = sorted(done | {rec_key(i) for i in idxs})
            cp["done_keys"] = fresh_keys
            done = set(fresh_keys)
            cp["stats"]["ok"] += stats["matched"]
            cp["stats"]["irrelevant"] += stats["irrelevant"]
            cp["stats"]["scored"] += stats["scored"]
            cp["stats"]["featured"] += stats["featured"]
            cp["stats"]["carrier_switched"] += stats["carrier_switched"]
            save_checkpoint(cp)
            pending_publish += 1
            if pending_publish >= PUBLISH_EVERY or idxs[-1] == todo[-1]:
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

#!/usr/bin/env python3
"""Backfill 未分类/补分类 —— 2026-09-28 起由 triage_engine 执行（旧 GLM 分类提示词退役）。

引擎是唯一分类与评分来源，新旧两套不得同时生效。本脚本保留原 CLI 接口：
  python scripts/backfill_categories.py [--max N] [--dry-run]

行为：
  1. 收集 lite 中 c == "未分类" 的记录
  2. 用 triage_engine（规则层 + 可选 LLM 复核）重新分诊（分类+类型+评分+精选）
  3. 保留人工/审核字段（lv/wr/cm），清除并按新规则重建 AI 派生字段
  4. 原子重建快照（build_snapshot）
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipeline"))

from build_snapshot import build_snapshot  # noqa: E402
import engine_triage  # noqa: E402

LITE_PATH = REPO / "pipeline" / "data" / "processed" / "all-records-lite.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=400)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    lite = json.loads(LITE_PATH.read_text(encoding="utf-8"))
    targets = [i for i, r in enumerate(lite) if r.get("c") == "未分类"][:args.max]
    print(f"未分类 targets: {len(targets)}")
    if not targets or args.dry_run:
        return 0

    batch = [dict(lite[i]) for i in targets]
    use_llm = not os.environ.get("TRIAGE_LLM_OFF")
    stats = engine_triage.engine_triage_records(
        batch, use_llm=use_llm,
        workdir=str(REPO / "pipeline" / ".engine_triage_work"),
    )
    print(f"engine stats: {stats}")
    for i, rec in zip(targets, batch):
        lite[i] = rec
    LITE_PATH.write_text(json.dumps(lite, ensure_ascii=False), encoding="utf-8")
    shards = build_snapshot(lite)
    print(f"snapshot rebuilt: {shards} shards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

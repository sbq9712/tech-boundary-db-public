# -*- coding: utf-8 -*-
"""triage_engine.cli —— 命令行入口。

用法示例：
  python -m triage_engine.cli version
  python -m triage_engine.cli run --news a.csv --wechat b.csv --literature c.csv --out OUT
  python -m triage_engine.cli run --batch-dir test/data/2660624-260630/2026-06-26 --out OUT
  python -m triage_engine.cli run --rows rows.json --out OUT --llm-decisions dec.json
  python -m triage_engine.cli llm --batch-dir ... --out OUT --batch 16 --sleep 6
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _collect_rows(args):
    from . import io_rows
    rows = []
    if args.rows:
        rows += io_rows.read_rows_json(args.rows)
    if args.news:
        rows += io_rows.read_news_csv(args.news)
    if args.wechat:
        rows += io_rows.read_wechat_csv(args.wechat)
    if args.literature:
        rows += io_rows.read_literature_csv(args.literature)
    if args.batch_dir:
        got, _files = io_rows.read_batch_dir(args.batch_dir)
        rows += got
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(prog="triage_engine", description="能源/零碳/AI 情报三库分类评分引擎 v1.07")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version", help="打印引擎版本")

    p_run = sub.add_parser("run", help="规则层全流程（分类→评分→档位政策→参考区→去重→四件套）")
    p_run.add_argument("--rows", help="行记录 JSON（list[dict]）")
    p_run.add_argument("--news", help="news-spider articles-*.csv")
    p_run.add_argument("--wechat", help="wechat 日报 csv")
    p_run.add_argument("--literature", help="literature news_with_abstract_*.csv")
    p_run.add_argument("--batch-dir", help="批次目录（news-spider/ wechat/ literature/ 扁平布局）")
    p_run.add_argument("--out", required=True, help="输出目录")
    p_run.add_argument("--llm-decisions", help="LLM 决策 JSON 路径（缺省=纯规则层）")

    p_llm = sub.add_parser("llm", help="LLM 语义判定层（需 .env / 环境变量）")
    p_llm.add_argument("--rows", help="行记录 JSON（list[dict]）")
    p_llm.add_argument("--news"); p_llm.add_argument("--wechat"); p_llm.add_argument("--literature")
    p_llm.add_argument("--batch-dir")
    p_llm.add_argument("--out", required=True)
    p_llm.add_argument("--batch", type=int, default=16)
    p_llm.add_argument("--sleep", type=float, default=6.0)
    p_llm.add_argument("--scoped", action="store_true", help="仅域外/T25/问题记录（默认全量）")
    p_llm.add_argument("--force-all", action="store_true")
    p_llm.add_argument("--dry-run", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "version":
        from . import ENGINE_VERSION, METHOD_TAG
        print(f"triage_engine v{ENGINE_VERSION}  method={METHOD_TAG}")
        return 0

    rows = _collect_rows(args)
    if not rows:
        print("[fatal] 未提供输入（--rows / --news / --wechat / --literature / --batch-dir）", file=sys.stderr)
        return 2
    print(f"输入行记录：{len(rows)} 条")

    if args.cmd == "run":
        from . import run
        result = run(rows, args.out, llm_decisions=args.llm_decisions)
        print(json.dumps(result["stats"], ensure_ascii=False))
        print(f"输出 → {os.path.abspath(args.out)}")
        return 0

    if args.cmd == "llm":
        from .llm import run_llm
        dec = run_llm(rows, args.out, batch=args.batch, sleep=args.sleep,
                      all_items=not args.scoped, force_all=args.force_all, dry_run=args.dry_run)
        print(f"judged={dec.get('judged')} accepted={dec.get('accepted')} skipped_low_conf={dec.get('skipped_low_conf')}")
        print(f"合并重建：python -m triage_engine.cli run ... --out {args.out} --llm-decisions "
              f"{os.path.join(args.out, 'llm_semantic_decisions.json')}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

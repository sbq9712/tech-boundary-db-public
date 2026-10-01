# -*- coding: utf-8 -*-
"""triage_engine.llm —— 可选 LLM 语义判定层（glm-5.2 / Anthropic Messages 协议，urllib 实现）。

对规则层的域外/T25/问题记录做语义复核（--all 时全量），产出 llm_semantic_decisions.json；
随后把它传入 engine.run(rows, out_dir, llm_decisions=<该文件路径>) 完成合并重建。

环境变量（.env 或进程环境，见 .env.example）：
  LLM_BASE_URL / LLM_API_KEY / LLM_MODEL（默认 glm-5.2）/ LLM_MAX_TOKENS（默认 4096）/
  LLM_TEMPERATURE（默认 0）/ LLM_TIMEOUT_SECONDS（默认 120）
"""
from __future__ import annotations

import json
import os
import sys

from .engine import load_base, _ensure_paths

_ensure_paths()
import run_llm_semantic_triage as _runner  # noqa: E402


def run_llm(rows, out_dir, batch=16, sleep=6.0, all_items=True, force_all=False, env=None,
            limit=0, dry_run=False):
    """执行 LLM 语义判定，返回 decisions dict。

    参数：
      rows: 与 engine.run 相同的行记录列表（判定范围圈定与去重在 runner 内完成）。
      out_dir: 写入 llm_semantic_audit.jsonl（断点续跑审计）与 llm_semantic_decisions.json。
      batch/sleep: 批大小与批间节流秒数（防 429；曾用 --batch 16 --sleep 6 稳定跑通全量）。
      all_items: True=全量判定；False=仅规则层域外/T25/问题记录。
      force_all: decisions 不过滤 confidence（默认只采纳 high 或规则层未决）。
      env: 可选 dict，合并进 os.environ（优先于 .env 中同名项之外的查找）。
    返回：llm_semantic_decisions.json 的完整 dict（version/model/judged/accepted/decisions…）。
    """
    base = load_base()
    base.read_rows = lambda: list(rows)
    if env:
        os.environ.update({k: str(v) for k, v in env.items()})
    _runner.AUDIT_PATH = os.path.join(out_dir, "llm_semantic_audit.jsonl")
    _runner.DECISIONS_PATH = os.path.join(out_dir, "llm_semantic_decisions.json")
    os.makedirs(out_dir, exist_ok=True)

    argv_backup = sys.argv[:]
    sys.argv = ["run_llm_semantic_triage"]
    if all_items:
        sys.argv.append("--all")
    if limit:
        sys.argv += ["--limit", str(limit)]
    if force_all:
        sys.argv.append("--force-all")
    if dry_run:
        sys.argv.append("--dry-run")
    sys.argv += ["--batch", str(batch), "--sleep", str(sleep)]
    try:
        _runner.main()
    finally:
        sys.argv = argv_backup

    with open(_runner.DECISIONS_PATH, encoding="utf-8") as f:
        return json.load(f)

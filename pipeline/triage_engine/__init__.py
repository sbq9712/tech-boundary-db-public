# -*- coding: utf-8 -*-
"""triage_engine —— 能源/零碳/AI 情报三库分类评分引擎（可调用包，v1.07）。

机制快照来源：outputs/github-triage-20260615-23 运行层（2026-09-23 v1.07，
= v1.04 分类规则 + v1.05 事件级去重 + v1.06(b) 论文统一档位 + v1.07 参考区）。

快速调用：
    from triage_engine import run
    result = run(rows, out_dir)          # rows: 行记录字典列表（schema 见 AI_INTERFACE.md）
    result["items"] / result["stats"]

可选 LLM 语义判定层：
    from triage_engine.llm import run_llm
    decisions = run_llm(rows, out_dir)   # 需要 .env（LLM_BASE_URL/LLM_API_KEY/LLM_MODEL）
"""
from .engine import run, load_base, load_strict, ENGINE_VERSION, METHOD_TAG

__version__ = ENGINE_VERSION
__all__ = ["run", "load_base", "load_strict", "ENGINE_VERSION", "METHOD_TAG", "__version__"]

# -*- coding: utf-8 -*-
"""triage_engine.engine —— 规则层分类评分入口（函数式封装，零第三方依赖）。

封装方式与 outputs/test-triage-* 测试 harness 同源同款（经过 06-24/25/26 三批验证）：
  sys.path 注入 pipeline/ 与 rules/ → import 两个管线模块 →
  monkeypatch base.read_rows（数据注入）→ s.HERE / s.LLM_DECISIONS_PATH（输出重定向）→
  s.validate（通用结构校验，无固定日期窗）→ s.build() → 读回 semantic_results.json。

注意：本引擎以全局模块名 build_github_triage / build_strict_semantic_triage 加载管线；
若宿主进程已从其他路径 import 过同名模块，会显式报错——请在子进程中运行引擎
（subprocess / 独立服务）即可隔离。
"""
from __future__ import annotations

import json
import os
import sys

PKG_ROOT = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.join(PKG_ROOT, "pipeline")
RULES_DIR = os.path.join(PKG_ROOT, "rules")

ENGINE_VERSION = "1.11"
METHOD_TAG = ("semantic-llm-calibrated-v5+three-band-scoring-v1.04+priority-tiers"
              "+s10-band-policy-v104+llm-merge+event-dedup-v105+paper-band-v106b+ref-zone-v107"
              "+future-roundup-retype-v108+display-chain-v109+doi-carrier-premise-v110"
              "+direct-banding-v111")

# v1.11 直评口径（用户 2026-09-25 修订）：不设 参考/待定/忽略 类目——入域直接三档，域外不评分。
OUTPUT_FILES = ("semantic_results.json", "semantic_results.csv",
                "域外内容分析_20260615-23.csv",
                "三库严格语义分类看板_20260615-23.html")

REQUIRED_ROW_KEYS = ("src", "date", "title")


def _ensure_paths():
    for p in (PIPELINE_DIR, RULES_DIR):
        if p not in sys.path:
            sys.path.insert(0, p)


def _guard(module, name):
    f = os.path.abspath(getattr(module, "__file__", ""))
    if not f.startswith(os.path.join(PIPELINE_DIR, "")):
        raise RuntimeError(
            f"模块名 {name!r} 已被其他路径的模块占用（{f}）。triage_engine 以全局名加载管线，"
            f"请勿在同一进程混用 outputs 运行层与本包；在子进程中运行引擎即可。")


def load_base():
    """加载（并缓存）管线基础模块 build_github_triage。"""
    _ensure_paths()
    import build_github_triage as base
    _guard(base, "build_github_triage")
    return base


def load_strict():
    """加载（并缓存）语义分类评分模块 build_strict_semantic_triage。"""
    _ensure_paths()
    import build_strict_semantic_triage as s
    _guard(s, "build_strict_semantic_triage")
    return s


def _check_rows(rows):
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("rows 必须是非空列表（行记录字典，schema 见 AI_INTERFACE.md）")
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            raise ValueError(f"rows[{i}] 不是 dict")
        missing = [k for k in REQUIRED_ROW_KEYS if not str(r.get(k) or "").strip()]
        if missing:
            # body 允许为空（content_quality=empty，管线有 T25/域外 兜底路径）
            raise ValueError(f"rows[{i}] 缺少必填字段 {missing}（src/date/title；body 可为空串）")
        if r.get("src") not in ("news-spider", "wechat", "literature"):
            raise ValueError(f"rows[{i}].src 必须是 news-spider/wechat/literature 之一，"
                             f"当前 {r.get('src')!r}")
        r.setdefault("body", "")


def _make_validator(out_dir):
    """通用结构校验（替代原 validate 的固定日期窗断言；v1.11 直评口径契约）。"""
    def validate(items, stats, outside_summary):
        assert items and stats["records"] == len(items), "记录数与 stats 不一致"
        assert all(x["domainRule"] and x["typeRule"] for x in items), "裁决规则字段缺失"
        outside = [x for x in items if x["domainDisp"] == "域外"]
        assert len(outside) == stats["outOfScope"] == outside_summary["total"], "域外计数不一致"
        assert all(x["outsideReason"] and x["outsideReasonDetail"] and x["outsideTopic"]
                   for x in outside), "域外记录缺结构化原因"
        assert all(not x["outsideReason"] for x in items if x["domainDisp"] != "域外")
        for key in ("reasons", "types", "topics", "sources"):
            assert sum(r["count"] for r in outside_summary[key]) == outside_summary["total"], key
        # v1.11 直评口径：不设 参考/待定/忽略 类目——入域直接三档，域外不评分。
        assert all(x["attention"] in ("高", "中", "低", "域外") for x in items), "存在 参考/待定/忽略 类目残留"
        assert all(x["attention"] == x["scoreBand"] for x in items
                   if x["domainDisp"] != "域外"), "入域记录缺三档"
        for fn in OUTPUT_FILES:
            p = os.path.join(out_dir, fn)
            assert os.path.isfile(p) and os.path.getsize(p) > 100, f"输出缺失或过小：{fn}"
    return validate


def run(rows, out_dir, llm_decisions=None):
    """执行规则层全流程（分类 → 评分 S1–S8 → S9 分层 → S10 档位政策 → 事件级去重
    → v1.11 直评口径 → 四件套输出）。

    参数：
      rows: 行记录字典列表。必填键：src(news-spider|wechat|literature)/date(ISO)/title/body；
            建议键：url/meta/doi/body_prep/content_quality(full|abstract|preview|digest|empty)。
      out_dir: 输出目录（不存在则创建）。写入四件套：
            semantic_results.json / semantic_results.csv / 域外内容分析_20260615-23.csv /
            三库严格语义分类看板_20260615-23.html。
            v1.11 直评口径：不设 参考/待定/忽略 类目——入域记录直接给 高/中/低（T02 走 S-R01
            粗分档、T25 经通用技术卡兜底、范围忽略仅审计）；域外不评分。主输出即全集。
      llm_decisions: None（纯规则层，默认）；或 LLM 决策 JSON 文件路径；或决策 dict
            （{"decisions": {url: {...}}} 或 {url: {...}}，schema 见 AI_INTERFACE.md §LLM）。

    返回：semantic_results.json 完整 dict：{"method", "stats", "outsideSummary", "items"}。
    """
    _check_rows(rows)
    base = load_base()
    s = load_strict()
    os.makedirs(out_dir, exist_ok=True)

    base.read_rows = lambda: list(rows)
    s.HERE = out_dir
    if llm_decisions is None:
        s.LLM_DECISIONS_PATH = os.path.join(out_dir, "__llm_decisions_absent__.json")
    elif isinstance(llm_decisions, dict):
        path = os.path.join(out_dir, "llm_semantic_decisions.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(llm_decisions, f, ensure_ascii=False)
        s.LLM_DECISIONS_PATH = path
    else:
        s.LLM_DECISIONS_PATH = str(llm_decisions)
    s.validate = _make_validator(out_dir)

    s.build()

    with open(os.path.join(out_dir, "semantic_results.json"), encoding="utf-8") as f:
        result = json.load(f)
    return result

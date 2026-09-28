# -*- coding: utf-8 -*-
"""triage_engine 集成测试（管线级，纯离线，不调外部 API）。

覆盖验收清单：
 1. 新闻档位 高/中 → AI精选；低 → 不精选
 2. 文献无论分数与档位 → 一律不进 AI精选
 3. 不相关 → 不评分、不精选、AI 派生字段清空（终止后续管线）
 4. 处理中情报不提前展示（= lite 中不存在"未评分/参考/待定"类用户可见终态标签；
    未评分仅允许作为引擎内部 scoreBand 状态，不落库）
 5. 重跑同一条情报不遗留旧 AI精选标记（档位降级/改判不相关两条路径）
 6. 主题/摘要/关键参数等其他字段不受引擎重跑影响
 7. 引擎域 → 主库 125 叶映射完整（163 域全部可解析；别名目标全部存在）
 8. 每条记录都能取回引擎结果（事件级并入不丢原记录）
"""
from __future__ import annotations

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.dirname(HERE)
sys.path.insert(0, PIPELINE)

import engine_triage as et  # noqa: E402


@pytest.fixture(scope="module")
def dom_map():
    return et.build_engine_domain_maps()


@pytest.fixture(scope="module")
def whitelist():
    return et.load_whitelist()


def make_item(**kw):
    base = {
        "date": "2026-09-01", "src": "news-spider", "meta": "", "title": "T", "url": "u",
        "doi": "", "duplicates": 0, "domain": "D01 光伏", "domainId": "pv_photovoltaic",
        "domainDisp": "主域", "domainConfidence": "明确", "domainRule": "R", "domainReason": "",
        "domainTerms": [], "domainSnippet": "", "secondaryDomains": [],
        "type": "T09 产品与装备", "typeId": "T09", "typeRule": "r", "typeReason": "",
        "typeEvidence": "", "typeAlternatives": [], "typeConfidence": "明确",
        "family": "", "card": "", "cardName": "", "priorityTier": "P1", "section": "主榜",
        "bandUnderlying": "中", "displayCategory": "新闻",
        "displaySubcategory": "工程与产业化", "displayClass": "B",
        "llmJudged": False, "value": 60.0, "valueDisplay": "60", "attention": "中",
        "scoreBand": "中", "scoreStatus": "已评分", "scoreRaw": 60, "scoreAfterGate": 60,
        "cap": "", "weight": "", "dimensions": [], "route": "", "routeTrlBand": "",
        "routeTrlBasis": "", "trl": "", "evidenceLevel": "E2", "gateActions": [],
        "missingEvidence": [], "scoreAudit": [], "ignored": "", "ignoredReason": "",
        "bodyPrep": "", "contentQuality": "full", "outsideReason": "",
        "outsideReasonDetail": "", "outsideTopic": "", "mergedRefs": [],
    }
    base.update(kw)
    return base


def apply(records, items, dom_map, whitelist):
    return et.apply_triage(records, {"result": {"items": items}}, dom_map, whitelist)


# ── 1. 新闻档位规则 ──
def test_news_band_high_and_medium_featured(dom_map, whitelist):
    recs = [et.__dict__ and {"t": "新闻高", "b": "", "u": "https://a/1", "d": "2026-09-01", "sr": "news/x.csv", "i": "n", "c": "", "tg": ""},
            {"t": "新闻中", "b": "", "u": "https://a/2", "d": "2026-09-01", "sr": "news/x.csv", "i": "n", "c": "", "tg": ""},
            {"t": "新闻低", "b": "", "u": "https://a/3", "d": "2026-09-01", "sr": "news/x.csv", "i": "n", "c": "", "tg": ""}]
    items = [make_item(url="https://a/1", title="新闻高", scoreBand="高", attention="高", value=80),
             make_item(url="https://a/2", title="新闻中", scoreBand="中", attention="中", value=60),
             make_item(url="https://a/3", title="新闻低", scoreBand="低", attention="低", value=40)]
    apply(recs, items, dom_map, whitelist)
    assert recs[0]["aip"] == 1
    assert recs[1]["aip"] == 1
    assert "aip" not in recs[2]
    # 分值刻度：引擎 0-100 → 前端 0-10
    assert recs[0]["sc"] == 8.0 and recs[2]["sc"] == 4.0


# ── 2. 文献一律不精选 ──
def test_literature_never_featured(dom_map, whitelist):
    recs = [{"t": "文献高分", "b": "", "u": "https://b/1", "d": "2026-09-01", "sr": "literature/x.csv", "i": "l", "c": "", "tg": ""}]
    items = [make_item(url="https://b/1", title="文献高分", src="literature", displayCategory="论文",
                       displaySubcategory="研究型", scoreBand="高", attention="高", value=92)]
    apply(recs, items, dom_map, whitelist)
    assert recs[0]["i"] == "l"
    assert recs[0]["tg"] == "研究论文"
    assert "aip" not in recs[0], "文献无论分数和档位都不进入 AI精选"
    assert recs[0]["sc"] == 9.2  # 分数照常保存


# ── 3. 不相关终止后续管线 ──
def test_irrelevant_terminates_pipeline(dom_map, whitelist):
    recs = [{"t": "域外新闻", "b": "x", "u": "https://c/1", "d": "2026-09-01", "sr": "news/x.csv",
             "i": "n", "c": "零碳产业/能量转化/能源测/一次能源转化/风电", "tg": "产业进展",
             "sc": 7.0, "scd": {"b": 1, "i": 2, "r": 3, "d": 4, "t": 5}, "aip": 1,
             "as": "旧摘要", "kp": ["参数"], "tp": "旧主题"}]
    items = [make_item(url="https://c/1", title="域外新闻", domainDisp="域外", domainId="",
                       domain="", displayCategory="—", displaySubcategory="域外",
                       scoreBand="未评分", attention="域外", value=None, valueDisplay="")]
    stats = apply(recs, items, dom_map, whitelist)
    r = recs[0]
    assert r["c"] == "不相关"
    assert r.get("sc") is None and "scd" not in r and "aip" not in r
    assert "as" not in r and "kp" not in r and "tp" not in r
    assert stats["irrelevant"] == 1


# ── 4. 无用户可见的 参考待定/未评分/高中低 终态标签落库 ──
def test_no_user_facing_band_labels(dom_map, whitelist):
    recs = [{"t": "T25兜底", "b": "", "u": "https://d/1", "d": "2026-09-01", "sr": "news/x.csv", "i": "n", "c": "", "tg": ""}]
    items = [make_item(url="https://d/1", title="T25兜底", typeId="T25", displayCategory="待定",
                       displaySubcategory="信息不足", scoreBand="中", value=58)]
    apply(recs, items, dom_map, whitelist)
    blob = json.dumps(recs[0], ensure_ascii=False)
    for banned in ("未评分", "参考", "待定", "高中低", "scoreBand", "attention"):
        assert banned not in blob, f"用户可见终态标签 {banned} 泄漏进记录"
    # T25 未定类型 → 默认标签，档位仍按引擎（中 → 新闻精选）
    assert recs[0]["tg"] == "行业观察"
    assert recs[0]["aip"] == 1


# ── 5. 重跑清除旧精选标记 ──
def test_rerun_clears_stale_featured(dom_map, whitelist):
    rec = {"t": "降级新闻", "b": "", "u": "https://e/1", "d": "2026-09-01", "sr": "news/x.csv",
           "i": "n", "c": "旧类", "tg": "行业观察", "sc": 8.8, "aip": 1}
    # 重跑后引擎改判"低"
    items = [make_item(url="https://e/1", title="降级新闻", scoreBand="低", attention="低", value=40)]
    apply([rec], items, dom_map, whitelist)
    assert "aip" not in rec, "旧 AI精选标记必须清除"
    assert rec["c"] != "旧类"  # 分类已更新为引擎结果

    # 重跑改判不相关路径
    rec2 = dict(rec, u="https://e/2", aip=1, c="旧类2")
    items2 = [make_item(url="https://e/2", title="降级新闻", domainDisp="域外", domainId="",
                        domain="", displayCategory="—", displaySubcategory="域外",
                        scoreBand="未评分", attention="域外", value=None, valueDisplay="")]
    apply([rec2], items2, dom_map, whitelist)
    assert "aip" not in rec2 and rec2["c"] == "不相关"


# ── 6. 其他 pipeline 字段不受影响 ──
def test_other_pipeline_fields_preserved(dom_map, whitelist):
    rec = {"t": "完整记录", "b": "正文", "u": "https://f/1", "d": "2026-09-01", "sr": "news/x.csv",
           "i": "n", "c": "旧类", "tg": "行业观察", "tp": "旧主题", "as": "旧摘要",
           "kp": ["关键参数"], "lv": 2, "wr": "预警词", "cm": "备注", "cl": 5, "dp": 0}
    items = [make_item(url="https://f/1", title="完整记录", scoreBand="中", value=60)]
    apply([rec], items, dom_map, whitelist)
    assert rec["tp"] == "旧主题" and rec["as"] == "旧摘要" and rec["kp"] == ["关键参数"]
    assert rec["lv"] == 2 and rec["wr"] == "预警词" and rec["cm"] == "备注"
    assert rec["cl"] == 5 and rec["dp"] == 0
    assert rec["aip"] == 1 and rec["sc"] == 6.0  # 新分类/评分已写入


# ── 7. 引擎域映射完整性 ──
def test_domain_map_total_coverage(dom_map, whitelist):
    assert len(dom_map) >= 160
    unresolved = [k for k, p in dom_map.items()
                  if p not in whitelist and et._E_TREE_ALIAS.get(p, p) not in whitelist]
    assert unresolved == [], f"未解析域: {unresolved}"
    bad_alias_targets = [v for v in et._E_TREE_ALIAS.values() if v not in whitelist]
    assert bad_alias_targets == []


# ── 8. 事件级并入不丢记录 ──
def test_merged_refs_index_no_record_loss(dom_map, whitelist):
    items = [make_item(url="https://g/1", title="主记录", scoreBand="高", value=80,
                       mergedRefs=[{"title": "并入记录", "src": "news-spider", "meta": "",
                                    "url": "https://g/2", "date": "2026-09-01",
                                    "band": "高", "value": 80}])]
    recs = [{"t": "主记录", "b": "", "u": "https://g/1", "d": "2026-09-01", "sr": "news/x.csv", "i": "n", "c": "", "tg": ""},
            {"t": "并入记录", "b": "", "u": "https://g/2", "d": "2026-09-01", "sr": "news/x.csv", "i": "n", "c": "", "tg": ""}]
    stats = apply(recs, items, dom_map, whitelist)
    assert stats["matched"] == 2 and stats["unmatched"] == 0
    assert recs[0]["aip"] == 1 and recs[1]["aip"] == 1  # 两条都取回同一引擎结果


# ── 9. 载体判定来自引擎（文献源里的媒体报道 → 新闻） ──
def test_carrier_from_engine_display_chain(dom_map, whitelist):
    rec = {"t": "媒体解读论文的新闻", "b": "", "u": "https://h/1", "d": "2026-09-01",
           "sr": "literature/x.csv", "i": "l", "c": "", "tg": "研究论文"}
    items = [make_item(url="https://h/1", title="媒体解读论文的新闻", displayCategory="新闻",
                       displaySubcategory="观点与交流", scoreBand="低", value=30)]
    apply([rec], items, dom_map, whitelist)
    assert rec["i"] == "n" and rec["tg"] == "行业观察"
    assert "aip" not in rec  # 新闻但档位低 → 不精选


# ── 10. T02 区间评分 ──
def test_t02_range_score_midpoint(dom_map, whitelist):
    rec = {"t": "行业报告", "b": "", "u": "https://i/1", "d": "2026-09-01", "sr": "news/x.csv", "i": "n", "c": "", "tg": ""}
    items = [make_item(url="https://i/1", title="行业报告", typeId="T02", value=None,
                       valueDisplay="55–69", scoreBand="中")]
    apply([rec], items, dom_map, whitelist)
    assert rec["sc"] == 6.2
    assert rec["aip"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

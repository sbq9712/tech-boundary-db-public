# -*- coding: utf-8 -*-
"""triage_engine 冒烟测试：合成 12 条行记录跑通规则层全流程，
覆盖 v1.07 机制（AI 模型发布题名锚定 T09）、v1.08 机制（S-A05 未来态计划低、
S-A04 常规发电汇总稿低、B1 媒体投资解读改判 T23）、v1.10 载体前提 C-T16
（DOI×语义共决：题名媒体框架×DOI → T23；全文转载本体载体 → T01）与
v1.11 直评口径（不设 参考/待定/忽略 类目：入域直接 高/中/低——T02 走 S-R01 粗分档；
域外不评分；主输出即全集、四件套）。
运行：PYTHONIOENCODING=utf-8 python -m pytest triage_engine/tests -q
  或：PYTHONIOENCODING=utf-8 python -m triage_engine.tests.test_smoke
"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
if PKG_ROOT not in sys.path:
    sys.path.insert(0, PKG_ROOT)

from triage_engine import run, ENGINE_VERSION  # noqa: E402

D = "2026-06-26"

AI_MODEL_TITLE = "第一个用物理做计算原语的大规模生成模型Un-0来了，或将AI能耗降低1000倍？"
AI_MODEL_BODY = (
    "今日，某研究院正式开源Un-0——第一个用物理做计算原语的大规模生成模型。"
    "该模型面向数据中心AI能耗问题，将物理仿真作为计算原语融入架构，官方称推理AI能耗或将降低1000倍。"
    "团队在发布会上展示了与主流大语言模型的对比评测：在同等算力能源基础设施条件下，"
    "Un-0的每token能耗显著下降，算力供电与数据中心能源开销同步减少。"
    "研究团队表示，下一步将与智算中心合作开展算力集群实测，验证AI用电规模的真实降幅。"
    "业内认为，若数据经第三方验证，将对算力能源基础设施的容量规划产生实质影响。"
) * 2

REPORT_TITLE = "中电联发布《2026年度电化学储能行业发展报告》：长时储能进入规模化应用初期"
REPORT_BODY = (
    "中电联今日发布《2026年度电化学储能行业发展报告》。报告 methodology 采用统计口径与数据来源双重校验，"
    "样本覆盖全国31个省份、超过1200个储能电站项目；问卷与调研周期为连续12个月，形成年度连续序列。"
    "统计范围包括锂电、液流、压缩空气等技术路线的装机、利用小时与调用数据，附录给出分区域明细。"
    "报告显示，长时储能项目逐渐增多，全钒液流电池进入规模化应用初期，同比增速达到45%。"
) * 2

ANALYSIS_TITLE = "深度解读：新型储能电价机制为何难落地——三省对比与机制出路"
ANALYSIS_BODY = (
    "本文基于公开数据来源与各地细则文件，对新型储能电价机制的落地难点进行解读。"
    "对比山东、甘肃、浙江三省的实践：一方面，容量补偿幅度与调用频次差异明显；"
    "另一方面，现货套利空间受充放次数与衰减成本制约。"
    "原因在于调节价值缺乏统一口径与传导渠道；结论是：机制设计需要厘清容量定价与电量定价的边界，"
    "并给独立储能电站稳定的预期收益框架。从产业反馈看，业主投资意愿仍受不确定性制约。"
) * 2

PAPER_TITLE = "Sulfide solid electrolytes for all-solid-state batteries: interface stability"
PAPER_BODY = (
    "Abstract: All-solid-state batteries promise higher energy density. We study sulfide solid "
    "electrolytes and their interface stability against lithium metal anodes. DOI 10.1000/demo1234. "
    "Experiments show improved critical current density; the model explains degradation mechanisms. "
    "（域内锚点：固态电池·硫化物电解质·锂金属负极研究，锂电池方向）"
)

OUT_TITLE = "某明星官宣新剧定档，粉丝社群狂欢与周边预售开启"
OUT_BODY = (
    "某明星今日官宣新剧定档，粉丝社群迅速开启庆祝话题。周边预售通道同步开启，"
    "多家电商平台上线联名商品。剧组发布先导预告片，播放量在数小时内突破千万。"
    "业内人士指出，粉丝经济带动周边消费，相关话题连续多日占据社交媒体热榜。"
) * 2

CATL_TITLE = "宁德时代发布新一代重卡换电电池包，配套换电站同步落地"
CATL_BODY = "宁德时代供应链动态：官方发布新一代重卡换电电池包，配套换电站规划同步公开。"

# ---- v1.08 裁决用例 ----
# W1：未来态里程碑（预计10月转入商业运营）→ S-A05 硬上限低
FUTURE_MILESTONE_TITLE = "乐山100MW/400MWh全钒液流储能电站预计10月转入商业运营"
FUTURE_MILESTONE_BODY = (
    "记者从项目方获悉，该全钒液流储能电站已完成主体建设与系统调试，预计10月转入商业运营。"
    "电站规模100MW/400MWh，采用全钒液流技术路线，将参与电网调峰与新能源消纳。"
    "项目方表示商业运营后将为区域电网提供长时储能支撑，后续视运行数据评估扩建。"
) * 2

# W3：常规发电项目汇总稿（多个×新能源项目×并网，晶硅光伏/风电常规组合）→ S-A04 硬上限低
GEN_ROUNUP_TITLE = "中国电建多个新能源项目并网发电！"
GEN_ROUNUP_BODY = (
    "近日，中国电建承建的多个新能源项目相继并网发电。其中甘肃某200MW光伏复合项目实现全容量并网，"
    "项目首个标段投产运行；内蒙古某风电基地一期机组并网成功，年发电量预计可达数亿千瓦时。"
    "上述项目涵盖晶硅光伏、常规风电机组与配套储能，进一步优化区域能源结构。"
) * 2

# B1：十五五媒体投资解读稿（无《》/发布/部委锚点，出炉+总投资将超框架）→ T19 改判 T23
POLICY_INTERP_TITLE = "“十五五”能源规划定调投资方向，光伏与电网总投资将超20万亿元"
POLICY_INTERP_BODY = (
    "随着新型能源体系建设“十五五”规划出台，市场普遍关注能源领域投资布局。"
    "综合各方测算，五年间光伏、风电与电网总投资将超20万亿元，电源侧与电网侧均有较大空间。"
    "分析认为，风光基地、跨区输电与灵活性资源是主要方向，产业链公司有望受益。"
) * 2

# v1.09 S-F01 窄修：T12 合作稿正文 boilerplate『全球首个+认证』背景句不得借首证地板抬档
COOP_BOILER_TITLE = "某钙钛矿企业与地方研究院签署战略合作协议，共拓应用新空间"
COOP_BOILER_BODY = (
    "双方今日签署战略合作协议，将在钙钛矿组件的示范应用与产线合作方面开展长期协作，"
    "研究院提供技术支撑，企业负责产业化推进，首批合作聚焦分布式光伏场景。"
    "背景资料：该企业曾宣称是全球首个通过国际第三方认证的钙钛矿组件企业，产线规模处于行业前列。"
) * 2

# ---- v1.10 载体前提（C-T16：DOI×语义共决，有 DOI ≠ 论文）用例 ----
# 假文献：题名媒体解读框架×正文 DOI 引用 → 不是文献本体，改判 T23 深度分析
DOI_FAKE_PAPER_TITLE = "深度解读：固态电解质界面机理新进展"
DOI_FAKE_PAPER_BODY = (
    "研究团队通过系统的实验表征与第一性原理仿真，揭示了硫化物固态电解质的界面离子输运机制；"
    "循环测试表明库仑效率与容量保持率均显著提升，机理分析与模型计算相互印证。"
    "本文原论文发表于国际期刊，DOI: 10.1038/xyz，读者可回查原文验证数据。"
    "编辑结合行业动态给出解读：界面稳定性仍是固态电池产业化的关键瓶颈。"
) * 2

# 真载体：《刊名》文章全文转载＋『引用本文』DOI → 论文本体，T01（v1.10 rescue 通道）
DOI_REPRINT_PAPER_TITLE = "《储能科学与技术》文章|ZIF-8衍生核壳Si@C负极的制备与电化学性能"
DOI_REPRINT_PAPER_BODY = (
    "本文为期刊全文转载。研究团队通过系统的实验表征与第一性原理仿真，设计了ZIF-8衍生的"
    "核壳结构Si@C负极材料；循环测试表明比容量与循环稳定性均显著提升，机理分析与模型计算相互印证。"
    "引用本文 DOI: 10.12028/j.cee.2026.0123，样品制备流程与对照实验详见原文。"
) * 2


def _rows():
    return [
        {"src": "wechat", "date": D, "title": AI_MODEL_TITLE, "url": "https://mp.weixin.qq.com/s/demo1",
         "meta": "新智元", "body": AI_MODEL_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "wechat", "date": D, "title": REPORT_TITLE, "url": "https://mp.weixin.qq.com/s/demo2",
         "meta": "能源局网站", "body": REPORT_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "news-spider", "date": D, "title": ANALYSIS_TITLE, "url": "https://news.example.com/3",
         "meta": "光伏行业协会", "body": ANALYSIS_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "literature", "date": D, "title": PAPER_TITLE, "url": "https://doi.org/10.1000/demo1234",
         "meta": "Joule RSS", "body": PAPER_BODY, "doi": "10.1000/demo1234", "body_prep": "",
         "content_quality": "abstract"},
        {"src": "news-spider", "date": D, "title": OUT_TITLE, "url": "https://news.example.com/5",
         "meta": "娱乐周刊", "body": OUT_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "news-spider", "date": D, "title": CATL_TITLE, "url": "https://news.example.com/6",
         "meta": "证券时报", "body": CATL_BODY, "doi": "", "body_prep": "", "content_quality": "preview"},
        {"src": "wechat", "date": D, "title": FUTURE_MILESTONE_TITLE, "url": "https://mp.weixin.qq.com/s/demo7",
         "meta": "储能产业观察", "body": FUTURE_MILESTONE_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "news-spider", "date": D, "title": GEN_ROUNUP_TITLE, "url": "https://news.example.com/8",
         "meta": "综合能源网", "body": GEN_ROUNUP_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "wechat", "date": D, "title": POLICY_INTERP_TITLE, "url": "https://mp.weixin.qq.com/s/demo9",
         "meta": "能源观察", "body": POLICY_INTERP_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "wechat", "date": D, "title": COOP_BOILER_TITLE, "url": "https://mp.weixin.qq.com/s/demo10",
         "meta": "钙钛矿观察", "body": COOP_BOILER_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "wechat", "date": D, "title": DOI_FAKE_PAPER_TITLE, "url": "https://mp.weixin.qq.com/s/demo11",
         "meta": "深科技观察", "body": DOI_FAKE_PAPER_BODY, "doi": "", "body_prep": "", "content_quality": "full"},
        {"src": "wechat", "date": D, "title": DOI_REPRINT_PAPER_TITLE, "url": "https://mp.weixin.qq.com/s/demo12",
         "meta": "储能科学与技术", "body": DOI_REPRINT_PAPER_BODY, "doi": "", "body_prep": "",
         "content_quality": "full"},
    ]


def _find(result, title_prefix):
    return next(x for x in result["items"] if x["title"].startswith(title_prefix))


def test_engine_smoke():
    assert ENGINE_VERSION == "1.11"
    with tempfile.TemporaryDirectory() as out_dir:
        result = run(_rows(), out_dir)

        # v1.11 直评口径：四件套产出（无第五件套《移出记录》）
        for fn in ("semantic_results.json", "semantic_results.csv",
                   "域外内容分析_20260615-23.csv",
                   "三库严格语义分类看板_20260615-23.html"):
            assert os.path.getsize(os.path.join(out_dir, fn)) > 100, fn
        assert result["method"].endswith("direct-banding-v111")
        assert result["stats"]["records"] == len(result["items"]) == 12  # 12 行全部留主输出

        # v1.11：不设 参考/待定/忽略 类目——attention 只剩 高/中/低/域外；审计位归零
        assert {x["attention"] for x in result["items"]} <= {"高", "中", "低", "域外"}
        assert not any(x["section"] == "参考区" for x in result["items"])
        stats = result["stats"]
        assert stats["refZone"] == 0 and stats["manual"] == 0
        assert all(x["attention"] == x["scoreBand"] for x in result["items"]
                   if x["domainDisp"] != "域外"), "入域记录缺三档"
        assert stats["high"] + stats["medium"] + stats["low"] + stats["outOfScope"] == 12

        # v1.07 #1：AI 模型发布（题名锚定 T09，不因正文发布会词误入 T24）
        ai = _find(result, "第一个用物理做计算原语")
        assert ai["typeId"] == "T09", ai["type"]
        assert ai["attention"] == "中" and ai["scoreBand"] == "中"  # S-P04 一般技术类地板
        assert ai["section"] == "主榜" and ai["priorityTier"] == "P0"

        # v1.11 直评：T02 报告不再入参考区，直接 S-R01 粗分档（方法＋样本＋连续性＋E1 → 高 75–89）
        rep = _find(result, "中电联发布")
        assert rep["typeId"] == "T02", rep["type"]
        assert rep["attention"] == "高" and rep["scoreBand"] == "高"
        assert rep["scoreStatus"] == "区间评分" and rep["valueDisplay"] == "75–89"
        assert rep["value"] is None  # 粗分档不伪造精确点分
        assert rep["section"] == "主榜"

        # v1.11 直评：T23 深度分析不再入参考区，按软信息上限直接 低
        ana = _find(result, "深度解读：新型储能电价机制")
        assert ana["typeId"] == "T23", ana["type"]
        assert ana["attention"] == "低" and ana["scoreBand"] == "低"

        # v1.08 W1：未来态里程碑（预计10月转入商业运营）→ S-A05 硬上限低·P2
        fut = _find(result, "乐山100MW/400MWh")
        assert fut["scoreBand"] == "低" and fut["attention"] == "低", fut["scoreBand"]
        assert fut["priorityTier"] == "P2"
        assert any("S-A05" in str(a) for a in (fut["gateActions"] + [str(r) for r in fut["scoreAudit"]]))

        # v1.08 W3：常规发电项目汇总稿（多个×并网，晶硅/风电常规组合）→ S-A04 硬上限低·P2
        rou = _find(result, "中国电建多个新能源项目")
        assert rou["scoreBand"] == "低" and rou["attention"] == "低"
        assert rou["priorityTier"] == "P2"
        assert any("S-A04" in str(a) for a in (rou["gateActions"] + [str(r) for r in rou["scoreAudit"]]))

        # v1.08 B1 + v1.11：十五五媒体投资解读稿 → T19 改判 T23 → 直接按机制出档（低）
        pi = _find(result, "“十五五”能源规划定调")
        assert pi["typeId"] == "T23", pi["type"]
        assert "媒体解读改判" in pi["typeRule"]
        assert pi["attention"] == "低" and pi["section"] == "主榜"

        # v1.09 S-F01 窄修：T12 合作稿正文 boilerplate『全球首个+认证』不得借首证地板抬档
        coop = _find(result, "某钙钛矿企业与地方研究院")
        assert coop["typeId"] == "T12", coop["type"]
        assert coop["scoreBand"] == "低" and coop["attention"] == "低", coop["scoreBand"]
        assert not any("S-F01" in str(g) for g in coop["gateActions"] if "地板" in str(g))

        # 文献载体 → T01（本例非正刊非瓶颈 → v1.06 统一中档）
        paper = _find(result, "Sulfide solid")
        assert paper["typeId"] == "T01" and paper["attention"] == "中"

        # v1.10 C-T16 假文献：题名『深度解读』媒体框架×正文 DOI 引用 → T23；
        # 正文『研究团队』构成科研转载载体证据 → S-P06 科研转载地板=中（科研转载不放低）
        fake = _find(result, "深度解读：固态电解质")
        assert fake["typeId"] == "T23", fake["type"]
        assert "C-T16" in fake["typeRule"], fake["typeRule"]
        assert fake["attention"] == "中" and fake["scoreBand"] == "中"
        assert any("S-P06" in str(a) for a in (fake["gateActions"] + [str(r) for r in fake["scoreAudit"]]))

        # v1.10 C-T16 rescue：《刊名》文章全文转载＋『引用本文』DOI → 论文本体 T01
        reprint = _find(result, "《储能科学与技术》文章")
        assert reprint["typeId"] == "T01", reprint["type"]
        assert reprint["attention"] == "中"
        assert reprint["displayCategory"] == "论文" and reprint["displaySubcategory"] == "研究型"

        # 域外不评分；范围忽略（CATL）仅审计字段，不再构成 忽略 类目
        out_rec = _find(result, "某明星官宣新剧")
        catl = _find(result, "宁德时代发布")
        for x in (out_rec, catl):
            assert x["domainDisp"] == "域外" and x["attention"] == "域外"
            assert x["scoreBand"] == "未评分" and x["value"] is None
        assert catl["ignored"] is True  # 审计留痕：范围忽略不再拦截评分/输出

        # v1.09 展示链路（纯展示标注，不影响评分）：论文/新闻两级 + 归入大类 A/B/C/D
        assert paper["displayCategory"] == "论文" and paper["displaySubcategory"] == "研究型" \
            and paper["displayClass"] == "A"
        assert fut["displayCategory"] == "新闻" and fut["displaySubcategory"] == "工程与产业化" \
            and fut["displayClass"] == "B(链2-5)"
        assert out_rec["displayCategory"] == "—"  # 域外 → 展示标域外
        assert sum(result["stats"]["displayChain"].values()) == result["stats"]["records"]

        # 档位分布闭合：高 1（T02 报告）/ 中 4（T09·T01×2·C-T16 假文献 S-P10）/ 低 5 / 域外 2
        assert (stats["high"], stats["medium"], stats["low"], stats["outOfScope"]) == (1, 4, 5, 2)

    print("triage_engine smoke OK：v1.07+v1.08+v1.09+v1.10+v1.11 机制（T09 题名锚定 / "
          "S-A05 未来态 / S-A04 汇总稿 / B1 媒体解读改判 / C-T16 载体前提（假文献→T23·全文转载→T01） / "
          "直评口径（12 条全留主输出：T02 S-R01 高 / T23 直接低 / 域外不评分·ignored 仅审计） / "
          "T01 中档 / 展示链路）全部落位")


if __name__ == "__main__":
    test_engine_smoke()

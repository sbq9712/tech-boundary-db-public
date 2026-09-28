# -*- coding: utf-8 -*-
"""三库大模型语义校准版分类看板。

分类阶段不计算 D/T 分：
- 领域：按标题和正文表达的主技术对象直接做语义判断；行业图景是优先基准，不是关键词门槛。
- 类型：按载体身份、必要条件、排除条件、跨类型边界和前置门禁逐级裁决。
- 新闻价值：领域与类型确定后，才调用 02 评分卡；分类证据不参与“选最高分”。
"""
from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.normpath(os.path.join(HERE, "..", "classification-scoring-rules-20260909"))
sys.path.insert(0, HERE)
sys.path.insert(0, RULES)

import build_github_triage as base
from cls_data import TYPES, DOMAIN_CLS, PRE_CLASSIFICATION_GATES, TYPE_DECISION_RULES
from expand_domains_data import EXPAND_DOMAINS, DOMAIN_DECISION_RULES, DOMAIN_PRIORITY_RULES
from score_data import PRIORITY_TIERS, BAND_POLICY_V103, BAND_POLICY_V104

TYPE_BY_ID = {t["id"]: t for t in TYPES}
# 资源体系沿用市场/供需变化卡，确保 T15 直接完成评分。
base.CARD_OF_TYPE["T15"] = "card_market"
# 2026-09-25 v1.11（用户口径修订）：不设"待定"类目——入域的 T25 记录经通用技术知识卡
# 兜底评分（base.score_card 的 CARD_OF_TYPE[T25] 原为 None，CARDS[None] 会 KeyError）；
# 类型仍记 T25（审计留痕），关注等级直接输出三档。
base.CARD_OF_TYPE["T25"] = "card_tech"
DOM_BY_ID = {d["id"]: d for d in base.DOMS}
DOM_BY_NO = {d["no"]: d for d in base.DOMS}

CONFIRMED_META = {x["domain_id"]: x for x in base.D["domain_cards"]}
EXPANDED_META = {x["id"]: x for x in EXPAND_DOMAINS}
EXPANDED_SLUG_TO_NO = {x["slug"]: x["id"] for x in EXPAND_DOMAINS}

LEVEL_ORDER = {
    "排他用途": 0,
    "专属路线": 1,
    "标题主对象": 2,
    "首段主对象": 3,
    "正文证据链": 4,
}

# 这些词单独出现时可能只是上位行业、材料用途或一般工程语境，需要第二个域内
# 语义要素消歧。未列入此表的专名、路线名、器件名和工艺名，本身即可证明域内。
AMBIGUOUS_OBJECT_TERMS = {
    "battery", "储能", "hydrogen", "fusion", "钙钛矿", "perovskite", "光热", "csp", "制冷", "散热", "冷板",
    "电机", "电驱", "能效", "电气化", "aqueous", "回收", "资源化", "管网", "勘探", "风机", "飞轮",
    "勘查", "开采", "品位", "生物基", "电催化", "合成气", "可降解", "稀土", "玻璃",
    "陶瓷", "硫酸", "电炉", "钢铁", "混凝土", "空压机", "压缩机", "低碳", "脱碳",
}

# 用户反馈校准后的同义表达。它们只帮助把自然语言映射到行业图景叶，不能累计分数。
# 行业图景已有路径时优先落原路径；target=E99/None 仅表示评分参数原先未登记，不表示域外。
SEMANTIC_ONLY_ALIASES_EXTRA = {
    10: ["地热", "地热能", "地热发电", "增强型地热", "EGS", "geothermal", "ocean energy", "tidal energy", "wave energy",
         # 2026-09-18：振动能/能量收集类英文文献标题召回（其他发电技术叶）
         "vibration energy", "energy harvesting", "triboelectric", "振动能", "摩擦纳米发电"],
    20: ["磷酸锰铁锂", "LMFP", "Li-SOCl2", "Li–SOCl2", "锂亚硫酰氯", "锂电正极", "锂电负极", "锂电电解质"],
    24: ["固态电解质", "准固态电解质", "凝胶电解质", "硫化物电解质", "氧化物电解质", "LLZO", "LATP"],
    85: ["视频生成模型", "生成式模型", "文本生成模型"],
    86: ["视频生成", "文生视频", "图生视频", "视觉生成", "知识密集型视频生成", "KIVI", "Sora", "Seedance"],
    87: ["模型基准", "模型评测", "基准评测", "提示词评测", "事实准确性评测"],
    99: ["光谱", "显微", "质谱", "色谱", "衍射", "科学仪器", "spectrometer", "microscope"],
    103: ["通信技术", "无线通信", "太赫兹通信", "可见光通信", "information transmission"],
    105: ["低空经济", "低空飞行", "eVTOL", "无人机产业", "低空装备", "飞行服务平台"],
    106: ["电动汽车", "充电网络", "智能充电", "自动驾驶", "robotaxi", "公路交通", "轨道交通"],
    109: ["基础物理", "核物理", "原子物理", "量子气体", "费米系统", "超导", "天体物理", "宇宙学", "gamma-ray", "supernova"],
    110: ["基础化学", "有机合成", "化学反应机理", "超分子", "配位化学", "skeletal editing"],
    111: ["医学", "生物学", "神经科学", "脑科学", "疾病", "药物", "免疫", "基因", "蛋白", "细胞", "微生物", "细菌", "病毒", "生态学", "植物学", "动物学", "brain", "bacterial", "microbial", "wildlife", "plant community"],
    116: ["铁电材料", "介电材料", "导电材料", "绝缘材料", "拓扑绝缘体"],
    117: ["导热材料", "耐热材料", "热界面材料", "隔热材料", "热电材料"],
    118: ["磁性材料", "自旋电子", "磁振子", "永磁材料", "软磁材料"],
    119: ["催化剂", "催化材料", "光催化", "电催化", "热催化"],
    120: ["结构材料", "高熵合金", "断裂韧性", "力学强度", "耐疲劳材料"],
    121: ["分离膜", "阻隔膜", "密封材料", "膜分离材料"],
    122: ["纳米工程", "纳米制造", "纳米结构", "纳米器件"],
    123: ["腐蚀", "防腐", "耐蚀", "抗腐蚀"],
    124: ["二维材料", "金属有机框架", "共价有机框架", "超材料", "MOF", "COF"],
    125: ["工艺工程", "过程强化", "制造工艺", "工业过程", "工程可靠性", "规模化制造"],
}

# 行业图景尚未显式列出、但本批新闻中反复出现且有稳定管理价值的扩展域。
# 扩展域同样直接评分，不进入待办状态。
EXTENSION_DOMAINS = [
    # 2026-09-18：E25 编号让位给注册域「碳市场与温室气体监测」（工作簿 03 v1.02），
    # 运行层扩展域改用 GT 序列，避免双义。
    {"no": "GT125", "id": "petrochemical_decarbonization", "name": "石化化工节能降碳",
     "status": "extended", "path": "扩展技术领域 > 工业脱碳 > 石化化工节能降碳",
     "rx": re.compile(r"石化|炼油|乙烯|烯烃|合成氨|化工行业|石油化工", re.I),
     "guard": re.compile(r"节能|降碳|减排|能效|电气化|改造|绿色转型|碳效", re.I)},
    {"no": "GT126", "id": "climate_risk_resilience", "name": "气候风险与基础设施韧性",
     "status": "extended", "path": "扩展技术领域 > 气候与环境 > 气候风险与基础设施韧性",
     "rx": re.compile(r"气候变化|气候风险|极端天气|风暴|热浪|洪水|干旱|野火|climate risk|extreme weather", re.I),
     "guard": re.compile(r"风险|损失|韧性|适应|影响|灾害|安全|保险|能源系统", re.I)},
    {"no": "GT127", "id": "digital_software_security", "name": "数字软件与信息安全",
     "status": "extended", "path": "扩展技术领域 > 数字技术 > 软件平台与信息安全",
     "rx": re.compile(r"网络安全|信息安全|数据安全|隐私计算|软件平台|操作系统|数据库|cybersecurity|data security|software platform", re.I),
     "guard": re.compile(r"技术|系统|平台|漏洞|攻击|防护|架构|算法|协议|安全", re.I)},
    {"no": "GT128", "id": "optoelectronic_emissive_devices", "name": "光电与发光器件",
     "status": "extended", "path": "扩展技术领域 > 光电技术 > 光电与发光器件",
     "rx": re.compile(r"PeLED|LED|发光二极管|发光器件|电致发光|光电器件|light-emitting\s+diode|electroluminescen", re.I),
     "guard": re.compile(r"器件|发光|效率|寿命|亮度|显示|光电|device|emission|efficien|lifetime|display", re.I)},
]

DOMAIN_EXTRA_ALIASES = {
    "li_battery": ["磷酸锰铁锂", "LMFP", "Li-SOCl2", "Li–SOCl2", "锂亚硫酰氯", "锂金属", "锂电正极", "锂电负极", "凝胶电解质"],
    "hydrogen_based_energy": ["可再生氢", "清洁氢", "低碳氢", "绿氢", "再生氢", "氢生产援助"],
    # 2026-09-18 复核补丁：钢铁碳中和类复合表达作为 D09 第二消歧要素（“钢铁”单词为歧义词）
    "steel_decarbonization": ["钢铁行业碳中和", "钢铁碳中和", "钢铁脱碳", "钢铁行业碳达峰", "steel decarbonization", "钢铁净零"],
    # 2026-09-19 v1.03：光电转换效率是光伏专属指标词（题名命中即 D01 标题主对象，
    # 防止“研制成功！光电转换效率26.2%刷新世界纪录”落通用技术叶）；叠层词表为钙钛矿叠层专属路线。
    "pv_photovoltaic": ["光电转换效率", "光电转化效率", "钙钛矿叠层", "全钙钛矿", "叠层光伏", "叠层组件", "perovskite tandem"],
    # 2026-09-19 v1.03：二氧化碳利用（CCU）词——CO2 作利用对象归 D12（作地热循环工质归 E26，见 E26 require）
    "ccus": ["二氧化碳利用", "二氧化碳资源化", "二氧化碳的开发", "CO2利用", "CO₂利用", "carbon utilization", "CO2 conversion"],
}

# 文献技术语义树中 target=None 只表示“尚未映射到 D/E 评分参数库”，不是域外。
# 这里补充新闻标题常用中文别名，英文正式术语仍直接来自文档的 en 字段。
SEMANTIC_ONLY_ALIASES = {
    85: ["大语言模型", "语言模型", "大模型", "文本生成", "自然语言处理", "生成式AI", "生成式人工智能",
         "ChatGPT", "GPT", "Claude", "Fable", "Gemini", "DeepSeek", "Llama", "Qwen", "通义千问", "豆包", "文心一言", "LLM",
         "OpenAI", "Anthropic"],
    86: ["多模态模型", "多模态大模型", "视觉语言模型", "视觉语言动作模型", "VLM"],
    87: ["模型压缩", "训练加速", "推理优化", "模型效率", "可解释AI", "AI安全", "模型安全", "模型评测", "越狱攻击"],
    88: ["AI4S", "科学智能", "人工智能科学发现", "机器学习材料", "机器学习化学", "AI实验设计"],
    89: ["半导体", "宽禁带", "氮化镓", "氧化镓", "碳化硅"],
    90: ["芯片", "集成电路", "AI加速器", "处理器架构", "存算一体", "神经形态芯片", "GPU", "NPU"],
    91: ["计算集群", "高性能计算", "超级计算机", "超级计算", "分布式训练", "算力集群"],
    92: ["数据中心", "智算中心", "算力中心"],
    93: ["算力能源基础设施", "算力供电", "AI能耗", "AI用电", "数据中心能源"],
    94: ["脑机接口", "神经接口", "神经解码", "神经调控", "连接组"],
    95: ["量子计算", "量子信息", "量子算法", "量子比特", "量子通信"],
    96: ["具身智能", "机器人基础模型", "具身操作系统", "具身智能体", "VLA"],
    97: ["人形机器人", "机器人控制", "机器人执行器", "灵巧手", "软体机器人", "机器人本体"],
    98: ["机器人换电", "机器人供能", "自主充电", "无人系统供能"],
}
for _leaf_no, _extra_terms in SEMANTIC_ONLY_ALIASES_EXTRA.items():
    SEMANTIC_ONLY_ALIASES.setdefault(_leaf_no, [])
    SEMANTIC_ONLY_ALIASES[_leaf_no] = list(dict.fromkeys(SEMANTIC_ONLY_ALIASES[_leaf_no] + _extra_terms))


def _semantic_only_leaf_rows():
    rows = []
    for leaf in base.LIT_LEAVES:
        if leaf.get("target") not in (None, "E99"):
            continue
        terms = list(dict.fromkeys([leaf["leaf"]] + list(leaf.get("en", [])) + SEMANTIC_ONLY_ALIASES.get(leaf["no"], [])))
        regexes = []
        for term in terms:
            if term in {"GPT", "Fable"}:
                rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?:[-\s]?[0-9][A-Za-z0-9.\-]*)?(?![A-Za-z0-9])", re.I)
            elif re.fullmatch(r"[A-Za-z0-9 .+&/\-]+", term):
                # 参考文档中的英文标准词多为单数；新闻和论文题名经常使用复数。
                # 允许末词 s/es 变化，避免 lithium metal batteries、proteins 等明确对象漏域。
                rx = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term).replace(r"\ ", r"\s+") +
                                r"(?:s|es)?(?![A-Za-z0-9])", re.I)
            else:
                rx = re.compile(re.escape(term), re.I)
            regexes.append((term, rx))
        prefix = "AI" if leaf["branch"] == "AI与智能科技" else "GT"
        rows.append({"no": f"{prefix}{leaf['no']}", "id": f"semantic_leaf_{leaf['no']}",
                     "name": leaf["leaf"], "status": "semantic-only", "path": leaf["path"],
                     "branch": leaf["branch"], "require": leaf.get("inc", ""), "rx": regexes})
    return rows


SEMANTIC_ONLY_DOMS = _semantic_only_leaf_rows()
AI_UMBRELLA_R = re.compile(r"人工智能|机器学习|Artificial\s+Intelligence|(?<![A-Za-z0-9])AI(?![A-Za-z0-9])", re.I)
AI_UMBRELLA_DOM = {"no": "AI00", "id": "semantic_branch_ai", "name": "AI与智能科技（待细分）",
                   "status": "semantic-only", "path": "AI与智能科技", "branch": "AI与智能科技",
                   "require": "明确以人工智能或机器学习为主对象"}

EVENT_R = re.compile(
    r"发布|推出|交付|投产|量产|并网|投运|建成|开工|签约|中标|招标|获批|立项|"
    r"测试|验证|运行|扩产|融资|收购|出台|印发|实施|认证|授权|申请|研究|开发|"
    r"launch|commission|deliver|validate|demonstrat|publish|develop", re.I)
NEGATION_R = re.compile(r"并非|不是|尚未|未能|否认|辟谣|不属于|not\s+(?:a|an|the)?", re.I)
BACKGROUND_R = re.compile(r"作为背景|背景是|顺带提及|例如|包括但不限于|相关领域还包括", re.I)


def _uniq(xs):
    return list(dict.fromkeys(x for x in xs if x))


def _hits(pairs, text):
    return _uniq([term for term, rx in pairs if rx.search(text)])


def _first_snippet(text, terms, width=72):
    for term in terms:
        m = re.search(re.escape(term.lstrip("※")), text, re.I)
        if m:
            a, b = max(0, m.start() - 24), min(len(text), m.end() + width)
            return re.sub(r"\s+", " ", text[a:b]).strip()
    return ""


def _specific_terms(terms):
    return [x for x in terms if x.lstrip("※").strip().lower() not in AMBIGUOUS_OBJECT_TERMS]


def _occurrences(text, terms):
    return sum(len(re.findall(re.escape(x.lstrip("※")), text, re.I)) for x in _uniq(terms))


def _meta_for(dom):
    if dom["id"] in CONFIRMED_META:
        m = CONFIRMED_META[dom["id"]]
        sem = DOMAIN_CLS.get(dom["id"], {})
        return {
            "require": sem.get("require", ""),
            "stage_words": m.get("stage_words", ""),
            "bottlenecks": [b.get("zh", "") for b in m.get("bottlenecks", [])],
        }
    m = EXPANDED_META.get(dom["no"], {})
    return {
        "require": m.get("require", ""),
        "stage_words": m.get("stage_words", ""),
        "bottlenecks": [b[1] for b in m.get("bottlenecks", [])],
    }


def _semantic_domain_candidate(item, dom):
    title, body = item["title"], item["body"]
    lead = body[:700]
    main = body[:2500]
    extra_pairs = []
    for term in DOMAIN_EXTRA_ALIASES.get(dom["id"], []):
        rx = base._en_matcher(term) if re.fullmatch(r"[A-Za-z0-9 .+&/\-–]+", term) else re.compile(re.escape(term), re.I)
        extra_pairs.append((term, rx))
    lit_pairs = []
    if item["src"] == "literature":
        lit_pairs.extend(dom.get("lit_r", []))
        for term, _rx0 in dom.get("lit_r", []):
            raw = term.lstrip("※")
            if re.fullmatch(r"[A-Za-z0-9 .+&/\-]+", raw):
                lit_pairs.append((term, re.compile(r"(?<![A-Za-z0-9])" + re.escape(raw).replace(r"\ ", r"\s+") +
                                                    r"(?:s|es)?(?![A-Za-z0-9])", re.I)))
    core_r = dom["core_r"] + extra_pairs + lit_pairs
    core_t, core_l, core_b = _hits(core_r, title), _hits(core_r, lead), _hits(core_r, main)
    ext_t, ext_l, ext_b = _hits(dom["ext_r"], title), _hits(dom["ext_r"], lead), _hits(dom["ext_r"], main)
    actors = _hits(dom["actors_r"], title + "\n" + main)
    meta = _meta_for(dom)
    stage_terms = [x for x in re.split(r"[|、,/（）()]+", meta["stage_words"]) if len(x.strip()) >= 2]
    stage_hits = [x.strip() for x in stage_terms if x.strip() in title + lead]
    bottleneck_hits = [x for x in meta["bottlenecks"] if x and x in title + main]
    metric_hits = []
    for unit in dom.get("units", []):
        if unit and re.search(r"\d+(?:\.\d+)?\s*" + re.escape(unit), title + main, re.I):
            metric_hits.append(unit)

    # D-G05：材料跨域时按器件用途。钙钛矿 LED/PeLED 是光电器件，不是光伏。
    if dom["no"] == "D01" and base._led_evidence(title + "\n" + lead) and not base.SOLAR_SIDE_R.search(title):
        return None

    route_hit = ""
    route_lead_hit = ""
    route_rx = base.DOMAIN_ROUTE_R.get(dom["no"])
    if route_rx:
        mt = route_rx.search(title)
        ml = route_rx.search(lead)
        if mt and not NEGATION_R.search(title[max(0, mt.start()-12):mt.end()+12]):
            route_hit = mt.group(0)
        elif ml and not NEGATION_R.search(lead[max(0, ml.start()-12):ml.end()+12]):
            route_lead_hit = ml.group(0)

    generic_units = {"%", "％", "-", "h", "MW", "GW", "GWh", "MWh", "kWh", "亿", "万", "元"}
    specific_metrics = [u for u in metric_hits if u not in generic_units]
    title_specific = _specific_terms(core_t)
    lead_specific = _specific_terms(core_l)
    body_specific = _specific_terms(core_b)
    if dom["no"] == "D01" and re.search(r"solar\s+cells?|photovoltaic", title, re.I):
        title_specific.append("solar cell")
    title_context = _uniq(core_t + ext_t + bottleneck_hits + specific_metrics + stage_hits)
    lead_context = _uniq(core_l + ext_l + ([route_lead_hit] if route_lead_hit else []) + bottleneck_hits + specific_metrics)
    body_chain = _uniq(core_b + ext_b + bottleneck_hits + specific_metrics)
    if route_hit:
        level, rule = "专属路线", "D-G03/D-G04"
    elif title_specific:
        level, rule = "标题主对象", "D-G02"
    elif core_t and (len(title_context) >= 2 or lead_specific or bottleneck_hits or specific_metrics):
        # 上位/歧义词不能独立入域，但只需第二个实质域内要素消歧；不要求动作或指标。
        level, rule = "标题主对象", "D-G02/D-G10"
    elif lead_specific:
        level, rule = "首段主对象", "D-G02"
    elif core_l and len(lead_context) >= 2:
        level, rule = "首段主对象", "D-G02/D-G10"
    elif body_specific and (_occurrences(main, body_specific) >= 2 or len(body_chain) >= 2) \
            and (core_t or ext_t or core_l or ext_l or lead_specific):
        # 正文中的明确对象需要具有中心性，避免侧带提及；动作/指标/瓶颈不是必要条件。
        # 2026-09-20 v1.04（M12）：题名/首段锚定——题名与首段全零、仅正文深部枚举/背景
        # 提及（『新三样』罗列锂电池）是侧带提及，不得硬分类到具体技术域（弱相关/域外）。
        level, rule = "正文证据链", "D-G02/D-G10"
    else:
        return None

    evidence_terms = _uniq(([route_hit or route_lead_hit] if (route_hit or route_lead_hit) else []) + core_t + core_l + ext_t + ext_l +
                           bottleneck_hits + metric_hits + stage_hits)[:8]
    source_text = title + "\n" + lead if level != "正文证据链" else main
    return {
        "dom": dom,
        "level": level,
        "rule": rule,
        "terms": evidence_terms,
        "snippet": _first_snippet(source_text, evidence_terms),
        "requirement": meta["require"],
        "title_object": bool(core_t or route_hit),
        "body_object": bool(core_l or core_b),
        "actor": actors[:2],
        "metric": metric_hits[:2],
        "route": route_hit,
    }


def _semantic_only_candidate(item):
    """识别文档中尚未挂接评分参数库的语义叶，分类有效但评分保持 null。"""
    title, lead = item["title"], item["body"][:900]
    candidates = []
    def semantic_hits(pairs, text):
        hits = []
        for term, rx in pairs:
            m = rx.search(text)
            if not m:
                continue
            around = text[max(0, m.start() - 18):min(len(text), m.end() + 18)]
            if NEGATION_R.search(around):
                continue
            # 2026-09-19 v1.03：机构名误中防护——“中科院半导体研究所”里的“半导体”
            # 是单位名的一部分，不是技术主对象；命中点紧邻院所后缀且前方是院所前缀时跳过。
            if re.search(r"(?:研究所|研究院|学院|大学)", text[m.end():m.end() + 4]) and \
                    re.search(r"(?:中科院|科学院|大学|理工|工业|航空|航天|军事|医科)", text[max(0, m.start() - 8):m.start()]):
                continue
            hits.append(term)
        return _uniq(hits)

    for dom in SEMANTIC_ONLY_DOMS:
        title_hits = semantic_hits(dom["rx"], title)
        lead_hits = semantic_hits(dom["rx"], lead)
        if not title_hits and not lead_hits:
            continue
        level = "标题主对象" if title_hits else "首段主对象"
        terms = _uniq(title_hits + lead_hits)[:8]
        # 题名命中优先；同层级取更具体、命中项更多的语义叶。
        key = (1 if title_hits else 0, len(title_hits), max((len(x) for x in terms), default=0),
               dom["path"].count(">"))
        candidates.append((key, dom, level, terms))
    if not candidates:
        m = AI_UMBRELLA_R.search(title) or AI_UMBRELLA_R.search(lead)
        if not m:
            return None
        level = "标题主对象" if AI_UMBRELLA_R.search(title) else "首段主对象"
        dom, terms = AI_UMBRELLA_DOM, [m.group(0)]
        return {
            "primary": dom, "secondary": [], "disp": "主域(语义域)",
            "confidence": "明确" if level == "标题主对象" else "可判",
            "rule": "D-G01/D-G02/语义树", "reason": (
                f"{level}明确属于文档一级分支“AI与智能科技”，但现有证据不足以细分到叶；评分参数未映射，不得判成域外"
            ),
            "terms": terms, "snippet": _first_snippet(title + "\n" + lead, terms),
            "label": f"{dom['no']} {dom['name']}", "candidates": [],
        }
    _key, dom, level, terms = max(candidates, key=lambda x: x[0])
    return {
        "primary": dom, "secondary": [], "disp": "主域(语义域)",
        "confidence": "明确" if level == "标题主对象" else "可判",
        "rule": "D-G01/D-G02/语义树", "reason": (
            f"{level}命中文档语义路径“{dom['path']}”；该叶尚未映射评分参数库，但不属于域外"
        ),
        "terms": terms, "snippet": _first_snippet(title + "\n" + lead, terms),
        "label": f"{dom['no']} {dom['name']}", "candidates": [],
    }


def _extension_domain_candidate(item):
    """匹配行业图景尚未显式列出、但主对象稳定明确的扩展技术域。"""
    title, lead = item["title"], item["body"][:1200]
    text = title + "\n" + lead
    matches = []
    for dom in EXTENSION_DOMAINS:
        obj = dom["rx"].search(title) or dom["rx"].search(lead)
        guard = dom["guard"].search(text)
        if not (obj and guard):
            continue
        level = "标题主对象" if dom["rx"].search(title) else "首段主对象"
        terms = _uniq([obj.group(0), guard.group(0)])
        matches.append((0 if level == "标题主对象" else 1, -len(obj.group(0)), dom, level, terms))
    if not matches:
        return None
    _a, _b, dom, level, terms = min(matches, key=lambda x: (x[0], x[1], x[2]["no"]))
    return {
        "primary": dom, "secondary": [], "disp": "主域(扩展)",
        "confidence": "明确" if level == "标题主对象" else "可判",
        "rule": "D-G01/D-G02/扩展域", "reason": (
            f"{level}明确为“{dom['name']}”；行业图景暂无专属叶，按文章主对象新增扩展域并直接纳入统一评分"
        ),
        "terms": terms, "snippet": _first_snippet(text, terms),
        "label": f"{dom['no']} {dom['name']}", "candidates": [],
    }


def classify_domain_semantic(item):
    title, lead = item["title"], item["body"][:700]

    # D-G05 排他用途：光电器件不误归光伏；按稳定主对象进入新增扩展域。
    if base._led_evidence(title + "\n" + lead) and not base.SOLAR_SIDE_R.search(title):
        ext = next(d for d in EXTENSION_DOMAINS if d["id"] == "optoelectronic_emissive_devices")
        return {
            "primary": ext, "secondary": [], "disp": "主域(扩展)", "confidence": "明确",
            "rule": "D-G05/扩展域", "reason": "器件功能为发光/光电输出，钙钛矿仅是材料，不归光伏；新增光电与发光器件域并直接评分",
            "terms": ["LED/发光器件"], "snippet": _first_snippet(title + "\n" + lead, ["LED", "发光"]),
            "label": f"{ext['no']} {ext['name']}", "candidates": []
        }

    candidates = [c for d in base.DOMS if (c := _semantic_domain_candidate(item, d))]
    semantic_only = _semantic_only_candidate(item)
    extension = _extension_domain_candidate(item)
    # 题名中的行业图景/AI/通用技术主对象优先于首段才出现的扩展域背景。
    if (semantic_only and semantic_only["confidence"] == "明确"
            and (not candidates or all(c["level"] in ("首段主对象", "正文证据链") for c in candidates))
            and (not extension or extension["confidence"] != "明确")):
        return semantic_only
    if extension and (not candidates or extension["terms"][0] in title):
        return extension
    # 语义树对象写在题名，而 D/E 候选只来自首段或正文时，以题名主对象为准。
    # 2026-09-19 v1.03：正文级别的语义叶不再抢先 D/E 参数域候选（参数库优先）；
    # 仅题名级语义叶（confidence=明确）可越过正文级 D/E 候选。
    if semantic_only and semantic_only["confidence"] == "明确" and \
            (not candidates or all(c["level"] in ("首段主对象", "正文证据链") for c in candidates)):
        return semantic_only
    if not candidates:
        if semantic_only:
            return semantic_only
        if extension:
            return extension
        return {
            "primary": None, "secondary": [], "disp": "域外", "confidence": "未满足必要条件",
            "rule": "D-G10", "reason": "通读标题与正文后，仍未发现能够落入行业图景或扩展技术域的主要技术对象",
            "terms": [], "snippet": "", "label": "", "candidates": []
        }

    # 专属叶优先于宽泛父域，规则来自 DOMAIN_PRIORITY_RULES；这里做布尔裁决，不累加分数。
    by_id = {c["dom"]["id"]: c for c in candidates}
    # 扩展域在运行对象中以 E## 为 id；规则表使用语义 slug。两者在裁决层对齐。
    by_key = dict(by_id)
    for slug, no in EXPANDED_SLUG_TO_NO.items():
        if no in by_id:
            by_key[slug] = by_id[no]
    for child, parent, pattern, decision in DOMAIN_PRIORITY_RULES:
        if child in by_key and parent in by_key and re.search(pattern, title + "\n" + lead, re.I):
            by_key[child]["rule"] = "D-G03"
            by_key[child]["reason_override"] = decision
            by_key[parent]["suppressed"] = True

    # 已登记的对象/环节边界。
    if re.search(r"制氢|电解槽|绿氢|海水制氢", title, re.I) and "hydrogen_based_energy" in by_id:
        for did in ("wind_power", "pv_photovoltaic"):
            if did in by_id:
                by_id[did]["suppressed"] = True
        by_id["hydrogen_based_energy"]["reason_override"] = "主产物或关键瓶颈是氢/电解槽，风光仅为能源来源"
    if re.search(r"氢冶金|直接还原铁|DRI|高炉|电炉", title, re.I) and "steel_decarbonization" in by_id:
        if "hydrogen_based_energy" in by_id:
            by_id["hydrogen_based_energy"]["suppressed"] = True
        by_id["steel_decarbonization"]["reason_override"] = "氢是工艺输入，最终应用对象是钢铁脱碳"
    if re.search(r"电芯|正极|负极|电解质|能量密度|循环寿命", title, re.I):
        if "storage_system" in by_id:
            by_id["storage_system"]["suppressed"] = True
    if re.search(r"储能电站|PCS|EMS|系统集成|并网|调度", title, re.I):
        for did in ("li_battery", "na_battery"):
            if did in by_id:
                by_id[did]["suppressed"] = True
    # 2026-09-19 v1.03（E26 require）：CO2 作地热循环工质时主对象是地热能利用；
    # “二氧化碳的开发/利用”类泛表达不得让 CCUS 抢走地热主事件的主域
    # （修复：『废气变暖气』地热供暖报道误归 D12）。
    if "E26" in by_id and re.search(r"地热|干热岩|超临界\s*CO2|supercritical\s+CO2|EGS",
                                    title + "\n" + item["body"][:900], re.I):
        if "ccus" in by_id:
            by_id["ccus"]["suppressed"] = True
            by_id["E26"]["reason_override"] = "二氧化碳是地热循环工质/取热介质，主对象为地热能利用（E26 require），不归 CCUS"
    # 典型父子域边界：专属对象优先，父域只保留为次域证据。
    specific_edges = [
        (r"燃料电池|电堆|PEMFC|膜电极", "E04", "hydrogen_based_energy", "用氢装置是研究对象，归燃料电池；氢能是上位背景"),
        (r"钠离子|钠电|sodium-ion", "na_battery", "li_battery", "钠离子体系是专属电池域，不归锂电"),
        (r"超级电容", "E10", "storage_system", "超级电容器是专属叶，储能为上位应用"),
        (r"光热电站|塔式光热|槽式光热|CSP", "E01", "storage_system", "光热电站是主资产，储能为配套功能"),
        (r"压缩空气储能|CAES|二氧化碳储能", "caes", "mechanical_storage", "压缩气体储能是登记专属域"),
    ]
    for pat, child, parent, why in specific_edges:
        if re.search(pat, title, re.I) and child in by_key:
            by_key[child]["reason_override"] = why
            if parent in by_key:
                by_key[parent]["suppressed"] = True

    active = [c for c in candidates if not c.get("suppressed")]
    # 极少数复合标题会同时触发相反方向的已登记边界。边界链不能把全部候选消掉；
    # 此时保留原候选并进入同级对象复核，而不是制造“域外”。
    if not active:
        for c in candidates:
            c.pop("suppressed", None)
        active = candidates
    active.sort(key=lambda c: LEVEL_ORDER[c["level"]])
    best_level = LEVEL_ORDER[active[0]["level"]]
    top = [c for c in active if LEVEL_ORDER[c["level"]] == best_level]

    # 多个同级主对象时按题名主语位置与术语具体度选主域；其它对象保留为附加参考。
    if len(top) > 1:
        def main_subject_key(c):
            positions = [title.lower().find(x.lstrip("※").lower()) for x in c["terms"]]
            positions = [x for x in positions if x >= 0]
            pos = min(positions) if positions else 10**6
            specificity = max((len(x.lstrip("※")) for x in c["terms"]), default=0)
            return (pos, -specificity, -c["dom"].get("path", "").count(">"))
        top.sort(key=main_subject_key)

    chosen = top[0]
    secondary = [c["dom"] for c in active[1:] if c["level"] in ("专属路线", "标题主对象", "首段主对象")][:3]
    disp = "主域(草案)" if chosen["dom"]["status"] == "draft" else "主域"
    confidence = "明确" if chosen["level"] in ("专属路线", "标题主对象") else "可判"
    reason = chosen.get("reason_override") or f"{chosen['level']}已明确目标技术对象：{chosen['requirement']}"
    if len(top) > 1:
        reason += "；复合主题按题名主语位置和专属术语具体度确定主域，其余仅作附加领域参考"
    return {
        "primary": chosen["dom"], "secondary": secondary, "disp": disp, "confidence": confidence,
        "rule": chosen["rule"], "reason": reason, "terms": chosen["terms"],
        "snippet": chosen["snippet"], "label": f"{chosen['dom']['no']} {chosen['dom']['name']}",
        "candidates": active
    }


def _rx(pattern, text):
    m = re.search(pattern, text, re.I)
    return m.group(0) if m else ""


def _cooccur(pattern_a, pattern_b, text, span=72):
    """两个语义要素必须位于同一短语/句段，避免从全文不同位置拼出伪事件。"""
    for seg in re.split(r"[。！？!?；;\n]", text):
        if len(seg) > 420:
            seg = seg[:420]
        ma, mb = re.search(pattern_a, seg, re.I), re.search(pattern_b, seg, re.I)
        if ma and mb and abs(ma.start() - mb.start()) <= span:
            return ma.group(0) + "＋" + mb.group(0)
    return ""


def classify_type_semantic(item):
    title, body = item["title"], item["body"]
    lead, text = body[:1200], title + "\n" + body[:2500]
    src = item["src"]

    if not body.strip() and not title.strip() and src != "literature":
        return type_result("T25", "C-G01", "标题和正文均缺失，无法识别新闻事件", "内容缺失", [], "信息不足")
    # 2026-09-18 复核补丁（C-T12 关联）：单主题学术速递（删链后仅存 digest）不是多事件合辑；
    # 3 篇以上才是合辑待拆分，单篇按速递载体照常分型。
    single_paper_digest = bool(_rx(r"学术速递|论文速递|研究进展速递|文献速递", title))
    if base.is_digest(item) and base._digest_multi_n(body) >= 3:
        return type_result("T25", "C-G03", "周报/合辑包含多个独立事件，应先拆分 Event", "集锦待拆分", [], "待复核")
    if src == "literature":
        ev = _rx(r"DOI|arXiv|Abstract|摘要|方法|结果|model|experiment", text)
        return type_result("T01", "C-G05/C-T01", "文献 RSS 载体身份优先，并存在题名/摘要结构", ev or "文献RSS", [], "明确")
    # 2026-09-18 约束3：单主题学术速递（含删链后仅存 digest 的微信文章）载体即 T01——
    # 标题已锚定唯一论文主事件，不以 DOI/论文链接缺失或正文不足为由落 T25。
    if single_paper_digest and base._digest_multi_n(body) < 3:
        return type_result("T01", "C-G05/C-T01-速递载体",
                           "单主题学术速递载体：标题锚定唯一论文主事件，已抓取 digest 即可用作判定（约束3：不得因删链/正文不足落待定）",
                           _rx(r"学术速递|论文速递|研究进展速递|文献速递", title) + "＋" + title[:30], [], "明确")
    # 2026-09-18 复核补丁（C-T10 载体形态优先）：直播预约/预告的主事件是一场活动，
    # 无论主题多学术都归 T24；正文引用的论文只是活动素材，不得反推 T01。
    # 2026-09-20 v1.04（M11）：会议预告同口径——『确认演讲/演讲嘉宾/嘉宾阵容/大会预告』
    # 的主事件是会议宣传，嘉宾介绍里的技术履历（九次世界纪录/cTÜVus 认证）只是素材。
    if _rx(r"直播预约|直播|webinar|livestream|live\s+stream|开播|预约直播|"
           r"确认演讲|确认出席|演讲嘉宾|重磅嘉宾|嘉宾阵容|大会预告|峰会预告|确认参会", title):
        return type_result("T24", "C-G02/C-T10", "标题主事件是直播/会议/活动预告；载体形态优先于内容命题，论文与嘉宾履历仅是活动素材",
                           _rx(r"直播预约|直播|webinar|livestream|开播|确认演讲|演讲嘉宾|嘉宾阵容|大会预告|峰会预告", title), [], "规则裁决")
    if re.search(r"影响因子|期刊分区|CiteScore|征稿|审稿周期|投稿链接|APC", title + "\n" + lead, re.I):
        return type_result("T21", "C-G02/T21-出版组织动态", "主事件是期刊或出版平台的运营指标、征稿或组织状态变化",
                           _rx(r"影响因子|期刊分区|CiteScore|征稿|审稿周期|投稿链接|APC", title + "\n" + lead), [], "语义裁决")
    # 标题明确写明招聘时，正文中的团队论文、期刊名和研究机制只是岗位背景，不能反向改判为论文。
    recruitment_title = _rx(r"招聘|诚聘|岗位|任职要求|应聘|简历投递|博士后", title)
    if recruitment_title:
        return type_result("T21", "C-G02/C-T05", "标题主事件是人才招聘；正文论文与技术成果仅用于介绍招聘团队",
                           recruitment_title, [], "语义裁决")

    # 2026-09-24 v1.10（C-T16 载体前提，用户口径）：literature 库一律文献（函数入口已判）；
    # wechat/news 判定"是否文献"须 DOI×语义共决——有 DOI 不一定是文献（可能是分析/报道）：
    #   ① 论文本体载体（《刊名》文章/全文转载/学术速递/网络首发/引用本文）→ 可 T01；
    #   ② DOI（字段/链接/正文）只是引用线索，不再单独构成论文载体；
    #   ③ DOI 迹象×题名媒体分析/报道框架（解读/盘点/Scientists 发现式转述等）→ 不是文献，
    #     改判 T23 深度分析（题名锚定，与 M1 同口径），DOI 记入证据链。
    doi_signal = bool(item.get("doi") or _rx(r"\b10\.\d{4,9}/\S+|arXiv[:\s]*\d+|\bDOI\b|doi\.org",
                                             (item.get("url") or "") + " " + text))
    paper_body_carrier = bool(_rx(r"《[^》]{2,20}》(?:文章|论文|全文)|学术速递|论文速递|研究进展速递|"
                                          r"文献速递|网络首发|引用本文", title + "\n" + lead))
    # 2026-09-20 v1.04（M11）：『发表于/刊登于』从论文结构证据中移除——报纸评论（经济日报
    # 专栏『构筑生产性服务业品牌矩阵』）同样有『发表于』，不足以判定论文载体。
    paper_structure = bool(_rx(r"论文标题|论文链接|文献详情|网络首发|摘要|DOI|arXiv|"
                                     r"JACS|AFM|Nature|Science|Joule|Angew|Advanced\s+Materials|"
                                     r"published\s+in|journal\s+article|paper\s+title", title + "\n" + lead))
    paper_claim = bool(_rx(r"机理|机制|模型|方法|实验|表征|样品|仿真|第一性原理|研究发现|研究团队|研究表明|研究显示|研究提出|研究|"
                                  r"identify|discover|demonstrat|mechanism|degradation|experiment|model|study|studies", text))
    industrial_title = bool(base.INDUS_TITLE_R.search(title))
    # v1.10：题名级媒体分析/报道框架词——DOI 迹象×此框架 ⇒ 引用论文的报道/分析稿，非文献本体。
    # （综述：/study shows/Scientists discover 属转述框架；全文转载/速递载体在上方 paper_body_carrier 先行豁免）
    media_analysis_frame = bool(_rx(r"解读|评述|评析|剖析|深度分析|盘点|梳理|知识分享|一文读懂|科普|评论|观点|详解|拆解|综述[：:｜]|"
                                            r"Top\s*\d+|周榜|月榜|据(?:报道|了解)|"
                                            r"科学家(?:发现|揭示)|研究者(?:发现|揭示)|[Ss]cientists?\s+(?:discover|find|reveal|turn)|"
                                            r"[Ss]tudy\s+(?:shows|finds|reveals|suggests)",
                                            title))
    if doi_signal and media_analysis_frame and paper_claim and not paper_body_carrier:
        return type_result("T23", "C-G05/C-T16-DOI载体前提",
                           "题名呈媒体分析/报道框架×DOI 引用线索——引用论文的报道/分析稿，非文献本体（有 DOI ≠ 论文）；"
                           "按主事件落深度分析，DOI 记入证据链",
                           _rx(r"解读|评述|评析|剖析|深度分析|盘点|梳理|知识分享|一文读懂|科普|评论|观点|详解|拆解|综述[：:｜]|"
                               r"Top\s*\d+|据(?:报道|了解)|[Ss]cientists?\s+(?:discover|find|reveal|turn)|"
                               r"[Ss]tudy\s+(?:shows|finds|reveals|suggests)", title)
                           + "＋DOI:" + (_norm_doi(item.get("doi")) or "正文/链接引用"),
                           [], "规则裁决")

    checks = []
    def add(tid, ok, rule, reason, evidence, certainty="明确"):
        if ok:
            checks.append({"tid": tid, "rule": rule, "reason": reason,
                           "evidence": evidence, "certainty": certainty})

    # v1.10（C-T16）：本体载体（全文转载/速递/网络首发）或题名/导语级论文结构锚定＋学术命题才可 T01；
    # 正文级 DOI 提及不再单独构成载体（DOI 归入 doi_signal 引用线索，配合媒体框架走 C-T16 改判）。
    add("T01", (paper_body_carrier and paper_claim) or (paper_structure and paper_claim and not industrial_title),
        "C-G05/C-T01", "论文载体或学术结构＋可识别学术命题", _rx(r"《[^》]{2,20}》|学术速递|网络首发|\b10\.\d{4,9}/\S+|DOI|论文|期刊|研究发现|机理|模型", text))
    add("T03", bool(_rx(r"(?:CN|US|WO|EP)\s*\d{6,}[A-Z]\d?|申请号|公开号|专利授权|无效宣告|专利许可", text)),
        "T03-必要条件", "存在专利文献标识或明确权利状态事件", _rx(r"(?:CN|US|WO|EP)\s*\d{6,}[A-Z]\d?|申请号|公开号|专利授权|无效宣告", text))
    add("T04", bool(_rx(r"软件著作权|软著|集成电路布图|植物新品种", text) and _rx(r"登记|授权|取得|转让|变更", text)),
        "T04-必要条件", "非专利技术权利客体＋登记或状态变化", _rx(r"软件著作权|软著|集成电路布图|植物新品种", text))
    add("T21", bool(_rx(r"招聘|诚聘|岗位|任职要求|应聘|简历投递|博士后", title + "\n" + lead)),
        "C-T05", "招聘对象、岗位或应聘方式优先于技术名词", _rx(r"招聘|诚聘|岗位|任职要求|应聘|博士后", title + "\n" + lead))
    standard_scope = title + "\n" + lead[:180]
    # 2026-09-20 v1.04（M10）：标准客体词补 规范/导则/技术规程——《压力管道规范 第5部分：
    # 氢用管道》实施是标准发布事件，不得落 T23 兜底。
    standard_pair = _cooccur(r"国家标准|行业标准|团体标准|技术标准|统一术语标准|标准|认证|许可|准入|法规|条例|技术规范|规范|导则|技术规程",
                             r"发布|实施|生效|修订|废止|通过|获得|颁发|批准|首发|adopt|approve|certif|license|effective",
                             standard_scope)
    standard_in_title = _rx(r"国家标准|行业标准|团体标准|技术标准|统一术语标准|标准|认证|许可|准入|法规|条例|技术规范|规范|导则|技术规程", title)
    add("T20", bool(standard_pair and standard_in_title and not _rx(r"报告|白皮书|政策解读", title)),
        "T20-必要条件", "同一短语内出现制度/认证客体与明确生效状态", standard_pair)
    policy_scope = title + "\n" + lead[:220]
    # 2026-09-18 复核补丁（C-T11）：行动部署词（开展/部署/目标/清零）与“N部门”联合发文表达纳入政策载体识别；
    # 吨位/金额/装机量只是政策量化目标，不得据此改判 T15/T16。
    policy_pair = _cooccur(r"通知|办法|意见|规划|行动方案|实施方案|申报指南|支持名单|征求意见|补贴|援助计划|资助计划|国家援助|政策|"
                                  r"开展|部署|清零|考核|考核办法|双控|专项行动|三年行动|五年行动|十五五|十四五|五年规划|国家重点研发|"
                                  r"policy|regulation|subsidy|rebate|incentive|government\s+program",
                           r"印发|发布|出台|实施|征求意见|申报|遴选|纳入|给予|支持|限制|禁止|"
                           r"批准|开展|部署|推动|目标|要求|完成|探析|路径|赋能|成长|下达|评价考核|"
                           r"launch|adopt|approve|allocate|restore|introduce|enact", policy_scope)
    policy_in_title = _rx(r"通知|办法|意见|规划|行动方案|实施方案|申报指南|支持名单|征求意见|补贴|援助计划|资助计划|国家援助|政策|"
                                 r"开展|部署|清零|考核|双控|专项行动|三年行动|五年行动|十五五|十四五|五年规划|国家重点研发|"
                                 r"policy|regulation|subsidy|rebate|incentive|government\s+program", title)
    # 2026-09-19 v1.03（C-T11 修订）：国家发展改革委等部门——「发展改革委」「等部门」此前不在正则内，
    # 导致重点行业政策落 T23。机关表达与部署动作齐全即 T19。
    official_title = _rx(r"发改委|发展改革委|发展和改革|能源局|工信部|财政部|生态环境部|住建部|交通运输部|政府|委员会|主管部门|"
                                r"[一二三四五六七八九十\d]+\s*部门|多部门|等部门|部门联合|部委|"
                                r"government|ministry|commission|authority|Austria|EU|European\s+Commission", title)
    add("T19", bool(policy_pair and (policy_in_title or official_title)), "C-T02/C-T03", "政策文件/措施与执行动作同现，并有题名身份或题名主管机构证据", policy_pair)
    bid_scope = title + "\n" + lead[:500]
    bid = _rx(r"招标|中标|采购|订单|候选人公示|框架采购|定点|tender|procurement|purchase\s+order|wins?\s+an?\s+order", bid_scope)
    boundary = _rx(r"金额|亿元|万元|数量|台|套|期限|截止|标段|合同|份额|候选人|MW|GW|GWh|MWh|\$|€|contract|deadline", bid_scope)
    add("T18", bool(bid and boundary), "C-T06", "采购义务＋可识别履行边界", bid + "＋" + boundary)
    # 2026-09-20 v1.04（M11）：技术风险/缺陷报道题名（工厂关闭/停产/硬伤＋技术对象）——
    # 正文里的融资履历与企业经营状态只是背景，不得反推 T13/T11/T16；主事件是技术风险
    # 分析，落 T23 后经 S-P07 实质技术案例/风险地板=中（『塑料热解工厂被迫关闭』案例）。
    tech_risk_title = bool(_rx(r"硬伤|缺陷|致命|被迫关闭|工厂关闭|关闭|停产|事故|爆炸|火灾|污染|安全风险", title)
                           and _rx(r"技术|工艺|热解|路线|材料|电池|储能|回收|碳|环保|节能|塑料", title))
    finance = _rx(r"融资|募资|增资|定增|战略投资|完成.{0,5}轮|A轮|B轮|C轮|基金投资|"
                         r"raises?|funding\s+round|investment\s+round|venture\s+funding", title + "\n" + lead)
    finance_term = _rx(r"亿元|万元|美元|轮融资|投资方|领投|跟投|估值|\$|€|valuation|investors?|led\s+by", title + "\n" + lead)
    add("T13", bool(finance and finance_term) and not tech_risk_title, "T13-必要条件",
        "融资交易主体＋金额、轮次或投资方", finance + "＋" + finance_term)
    ma = _rx(r"收购|并购|出售|资产转让|股权转让|控制权|要约收购|acquire|acquisition|merger|to\s+buy|sells?", title + "\n" + lead)
    add("T14", bool(ma and _rx(r"股权|股份|资产|控制权|交易对价|持股|shares?|assets?|stake|\$|€", title + "\n" + lead)), "T14-必要条件",
        "交易行为＋控制权或关键资产转移", ma)
    test_act = _rx(r"第三方检测|第三方测试|认证测试|横评|Benchmark|基准测试|抽检|检测报告|经.{0,30}(?:验证|认证)|validated|certified", text)
    test_ind = _rx(r"TÜV|SGS|UL|中汽研|检测中心|认证机构|独立实验室|研究所|科学院|Institute|Academy|第三方", text)
    add("T06", bool(test_act and test_ind), "T06-必要条件", "独立测量主体＋测试行为或规程", test_ind + "＋" + test_act)

    report_obj = _rx(r"报告|白皮书|路线图|蓝皮书|数据集|统计年鉴|report|white\s+paper|roadmap", title + "\n" + lead)
    report_system = _rx(r"样本|调研|方法|口径|数据来源|章节|问卷|统计范围|附录|CAGR|methodology|survey|sample|dataset", text)
    report_carrier = _rx(r"发布.{0,16}(?:报告|白皮书|路线图)|《[^》]{2,80}(?:报告|白皮书|路线图)》|"
                                r"(?:releases?|publishes?)\s+(?:an?\s+)?(?:report|white\s+paper|roadmap)", title + "\n" + lead)
    add("T02", bool(report_obj and report_carrier and report_system), "C-T01/C-T09",
        "可定位的报告载体＋系统方法、样本或统计口径", report_carrier + "＋" + report_system)

    rd_obj = _rx(r"国家重点研发计划|科研项目|研发计划|专项课题|课题编号|基金资助|揭榜挂帅|联合研发计划", text)
    rd_state = _rx(r"立项|获批|启动|资助|结题|验收|延期|承担|牵头", text)
    add("T05", bool(rd_obj and rd_state), "C-T03/T05-必要条件", "具体科研计划或课题实体＋资源承诺/状态变化", rd_obj + "＋" + rd_state)
    validation_obj = _rx(r"样机|原型|系统|装置|车辆|电堆|组件|设备|工程|prototype|system|device|vehicle|module", title + "\n" + lead)
    validation_act = _rx(r"完成.{0,12}(?:测试|试验|验证)|通过.{0,12}(?:测试|验证)|道路测试|试飞|示范运行|实车测试|连续运行|"
                                r"completes?\s+(?:a\s+)?test|demonstrat(?:es|ed|ion)|pilot\s+test|road\s+test|flight\s+test", text)
    add("T07", bool(validation_obj and validation_act and not _rx(r"计划|拟|将|预计", title)
                    and not _rx(r"合作|协议|签约", title)), "C-T04/T07-必要条件",
        "技术或工程系统＋已经发生的特定环境验证", validation_obj + "＋" + validation_act)
    operation_scope = title + "\n" + lead[:180]
    operation_pair = _cooccur(r"产线|工厂|电站|机组|装置|矿山|项目|\bplant\b|\bfactory\b|\bfacility\b|\bstation\b|production\s+line",
                              r"投产|量产|产出合格产品|打通全流程|产量|出货量|发电量|利用小时|良率|开工率|负荷率|连续运行|开始.{0,6}运行|商业运行|投入运行|爬坡|满产|运营数据|"
                              r"begins?\s+operat|starts?\s+operat|commissioned|comes?\s+online|output|shipments?|generation",
                              operation_scope)
    operation_entity = operation_pair.split("＋", 1)[0] if operation_pair else ""
    operation_act = _rx(r"投产|量产|产出合格产品|打通全流程|产量|出货量|发电量|利用小时|良率|开工率|负荷率|连续运行|商业运行|投入运行|开始.{0,6}运行|爬坡|满产|运营数据|"
                               r"begins?\s+operat|starts?\s+operat|commissioned|comes?\s+online|output|shipments?|generation", text)
    operation_title_entity = _rx(r"产线|工厂|电站|机组|装置|矿山|项目|\bplant\b|\bfactory\b|\bfacility\b|\bstation\b|production\s+line", title)
    add("T10", bool(operation_pair and operation_title_entity and operation_act and _rx(r"已|成功|投产|量产|实现|达到|开始|投入|同比|环比|累计|本月|季度|年度|"
                                                                    r"begins?|starts?|commissioned|online|achieved|annual|quarter", operation_scope)),
        "C-T04/T10-必要条件", "已投运实体＋周期化真实运行数据或状态变化", operation_entity + "＋" + operation_act)
    project_scope = title + "\n" + lead[:180]
    # 2026-09-18 复核补丁（C-T13）：水库/大坝/reservoir 等设施实体与扩建/扩容/expansion 等跃迁动作纳入
    # 2026-09-20 v1.04（M4）：商业化运营/正式运营/转入运营/全流程贯通是运营态跃迁——
    # 『全球首套！首钢朗泽…项目商业化运营』不得落 T23 兜底。
    project_pair = _cooccur(r"项目|基地|园区|工厂|电站|产线|设施|水库|大坝|\bproject\b|\bplant\b|\bfactory\b|\bfacility\b|\bfarm\b|reservoir|production\s+line",
                            r"核准|备案|公示|废止|终止|开工|奠基|建设|吊装|封顶|建成|投产|并网|投运|竣工|签约|进洞|倒送电|扩建|扩容|扩机|升级改造|"
                            r"商业化运营|商业运营|正式运营|转入运营|转入商业运营|全流程贯通|全工艺流程贯通|"
                            r"to\s+build|will\s+build|set\s+up|breaks?\s+ground|construction|commission|proposes?|plans?|expansion|upgrade|revamp", project_scope)
    project_title_entity = _rx(r"项目|基地|园区|工厂|电站|产线|设施|水库|大坝|\bproject\b|\bplant\b|\bfactory\b|\bfacility\b|\bfarm\b|reservoir|production\s+line", title)
    add("T08", bool(project_pair and project_title_entity), "C-T04/T08-必要条件", "题名出现项目/设施实体，并在同一事件单元内发生阶段状态跃迁", project_pair)
    product_scope = title + "\n" + lead[:160]
    # 2026-09-23 v1.07（#1）：题名锚定的 AI 模型发布事件补 生成模型/生成式模型/基础模型 与
    # 来了/亮相/开源——『第一个用物理做计算原语的大规模生成模型Un-0来了』主事件是模型发布，
    # 不因正文提及发布会/大会（T24 会议证据来自正文杂质）而误入会议卡低档。
    ai_model_obj = _rx(r"GPT(?:[-\s]?[0-9][A-Za-z0-9.\-]*)?|ChatGPT|Claude|Fable(?:[-\s]?[0-9][A-Za-z0-9.\-]*)?|"
                       r"Gemini|DeepSeek|Llama|Qwen|通义千问|豆包(?:大模型)?|文心一言|大语言模型|大模型|语言模型|"
                       r"生成模型|生成式模型|基础模型|\bLLM\b", title)
    ai_model_state = _rx(r"发布|推出|上线|开放|下线|停售|停服|撤回|移除|关闭|暴毙|封禁|禁用|延迟|推迟|延期|复活|泄露|实测|"
                         r"来了|亮相|开源|"
                         r"launch|release|delay|ban|suspend|available|deprecat", title)
    product_pair = _cooccur(r"产品|设备|装备|组件|电芯|电池|电解槽|逆变器|型号|product|device|module|cell|electroly[sz]er|inverter|model",
                            r"发布|推出|上市|发售|交付|量产|规格|参数|效率|容量|功率|寿命|认证|launch|unveil|release|deliver|commercial|specification|efficiency|capacity",
                            product_scope, 54)
    product_title_obj = _rx(r"产品|设备|装备|组件|电芯|电池|电解槽|逆变器|型号|\bproduct\b|\bdevice\b|\bmodule\b|\bcell\b|electroly[sz]er|inverter|\bmodel\b", title)
    product_release = _rx(r"发布|推出|上市|发售|交付|量产|launch|unveil|release|deliver|commercial", product_scope)
    add("T09", bool(product_pair and product_title_obj and (product_release or re.search(r"\d", title))
                         and not project_pair and not _rx(r"报告|白皮书|report|white\s+paper", title)),
        "T09-必要条件", "题名产品实体＋同一语义单元内的阶段、参数或规格", product_pair)
    cooperation = _rx(r"战略合作|合作协议|联合开发|共同开发|签署协议|成立联盟|合资|partners?\s*with|partnership|joint\s+development|agreement", title + "\n" + lead)
    add("T12", bool(cooperation and _rx(r"与|和|联合|双方|两家|with|between|joint", title + "\n" + lead)), "T12-必要条件",
        "两个可识别主体＋合作行为", cooperation)
    supply = _rx(r"断供|短缺|供应链|供应商替代|国产替代|供应迁移|供应中断|产能外迁|节点迁移", text)
    # 2026-09-20 v1.04（M11）：题名是技术应用案例/解析表达（如何/案例/实践/解密/解析）且
    # 题名无供应词时，正文的供应链背景不得反推 T17；主事件是技术案例，落 T23 经 S-P07。
    case_title = bool(_rx(r"如何|案例|实践|解密|解析", title))
    supply_title = bool(_rx(r"供应|短缺|断供|替代|迁移|供应链|采购|产能", title))
    add("T17", bool(supply and _rx(r"供应|采购|产能|节点|替代|迁移|短缺", text)) and not (case_title and not supply_title),
        "T17-必要条件", "供应关系或节点＋结构性变化", supply)
    market_scope = _rx(r"市场|价格|现货|期货|出口|进口|贸易|份额|销量|装机量|market|price|exports?|imports?|sales|installations?|capacity\s+additions?", title + "\n" + lead)
    market_change = _rx(r"上涨|下跌|增长|下降|同比|环比|成交|达到|减少|增加|创下|收窄|扩大|rises?|falls?|grows?|declines?|adds?|reaches?|curtails?", title + "\n" + lead)
    add("T16", bool(market_scope and market_change and _rx(r"%|％|亿元|万吨|GW|GWh|美元|元/|\$|€", text)) and not tech_risk_title,
        "T16-必要条件", "已实现市场变化＋市场范围和量化口径", market_scope + "＋" + market_change)
    resource = _rx(r"矿产资源|矿床|储量|资源量|锂矿|镍矿|钴矿|稀土矿|品位|开采权", text)
    add("T15", bool(resource and _rx(r"吨|万吨|储量|资源量|品位|开采|投产", text)), "T15-必要条件",
        "资源体＋数量、品位或开采状态", resource)
    enterprise = _rx(r"营收|利润|亏损|财报|业绩|破产|重组|裁员|停产|复产|退市", title + "\n" + lead)
    add("T11", bool(enterprise and _rx(r"同比|环比|亿元|万元|扭亏|预亏|增长|下降|申请", text)) and not tech_risk_title,
        "T11-必要条件", "企业经营状态发生可验证的实质变化", enterprise)
    meeting = _rx(r"会议|论坛|峰会|研讨会|评审会|发布会|大会|展会|博览会|直播|conference|forum|summit|symposium|expo|convention|webinar|livestream", title + "\n" + lead)
    meeting_info = _rx(r"召开|举办|出席|议程|参会|展示|展品|主办|承办|预约|报名|开播|held|hosts?|agenda|attends?|exhibits?", title + "\n" + lead)
    add("T24", bool(meeting and meeting_info), "C-T07/T24-必要条件", "可识别活动＋议程、出席或展品信息", meeting + "＋" + meeting_info, "可判")
    viewpoint = _rx(r"表示|认为|指出|建议|呼吁|预测|接受采访|访谈|演讲|发言", title + "\n" + lead)
    speaker = _rx(r"董事长|院士|教授|专家|研究员|负责人|总经理|CEO|部长|主任", title + "\n" + lead)
    add("T22", bool(viewpoint and speaker), "C-T08/T22-必要条件", "可识别发言人＋实质观点", speaker + "＋" + viewpoint, "可判")
    analysis = _rx(r"分析|解读|评论|观察|复盘|洞察|趋势|为什么|如何看待|产业链梳理|技术路线|作用机制|推进路径|"
                   r"analysis|review|outlook|trend|why|how", title + "\n" + lead)
    analysis_chain = _rx(r"数据来源|根据.{0,20}数据|对比|原因在于|一方面|另一方面|结论|推演|框架|according\s+to|data|compared|because|conclusion|framework", text)
    add("T23", bool(analysis and analysis_chain and len(body) >= 300), "C-T08/T23-必要条件",
        "原创分析主题＋数据、比较或推理链", analysis + "＋" + analysis_chain, "可判")

    policy_commentary = bool(len(body) >= 500 and _rx(r"改革|治理|人才机制|行动计划|政策体系|节能降碳", title + "\n" + lead)
                             and _rx(r"指出|强调|认为|应当|必须|有利于|一方面|另一方面|总体而言|关键在于", text))
    add("T23", policy_commentary and not policy_pair, "C-T08/T23-政策评论",
        "正文主要解释政策、制度或产业问题，并形成连续论证，不是新政策发布事件", _rx(r"改革|行动计划|指出|强调|关键在于", text), "语义裁决")

    # AI 模型是软件产品/型号；题名中的发布、封禁、延期等可用状态优先于正文旁支交易词。
    if ai_model_obj and ai_model_state:
        return type_result("T09", "C-G02/C-T09", "题名主事件为具名AI模型的发布或可用状态变化",
                           ai_model_obj + "＋" + ai_model_state, [x["tid"] for x in checks if x["tid"] != "T09"], "规则裁决")
    if re.search(r"气候变化|气候风险|极端天气|风暴|热浪|洪水|干旱|野火", text, re.I) and not re.search(r"市场|价格|交易|贸易|份额|销量", title, re.I):
        return type_result("T23", "C-G02/T23-气候知识", "主事件是气候风险数据的解释与知识传播，不是市场价格或交易状态变化",
                           _rx(r"气候变化|气候风险|极端天气|风暴|热浪|洪水|干旱|野火", text), [x["tid"] for x in checks if x["tid"] != "T23"], "语义裁决")

    if not checks:
        # 2026-09-18 复核补丁（C-T13）：标题含明确阶段状态跃迁/纪录动作时不得落 T23 知识兜底。
        title_event = _rx(r"开工|奠基|建成|投产|并网|投运|竣工|封顶|扩容|扩建|发布|推出|上市|交付|量产|破纪录|世界纪录|首创|首次|"
                          r"商业化运营|商业运营|正式运营|全流程贯通|"
                          r"begins?|starts?|breaks?\s+ground|commissioned|comes?\s+online|unveil|launch|record", title)
        if title_event:
            return type_result("T08", "C-G02/C-T13", "标题主事件是设施/项目的阶段状态跃迁；事件动作优先于知识解释叙事，不落 T23 兜底",
                               title_event, [], "规则裁决")
        # 2026-09-19 v1.03b（C-T13-首段跃迁）：checks 为空时同样合成首段主事件——
        # 『废气变暖气』类标题党把『我国首个＋投产』写在正文首段，此前此分支直接落 T23 兜底。
        first_lead = re.search(r"(?:我国|国内|全球|世界)(?:首个|首次|首套|首创)[^\n]{0,80}?"
                               r"(?:投产|投运|建成|并网|运行)", body[:1400], re.I)
        named_actor = re.search(r"(?:院|公司|集团|大学|研究所|分公司|学会|协会|专委会|企业|工厂|部门)", body[:1400])
        if first_lead and named_actor:
            return type_result("T08", "C-G02/C-T13-首段跃迁",
                               "标题为科普/悬念式表达，正文首段锚定『首个＋投产/投运』具名项目主事件；主事件取首段而非标题修辞",
                               re.sub(r"\s+", " ", first_lead.group(0))[:40], [], "规则裁决")
        if len(body) >= 300:
            return type_result("T23", "C-G01/T23-语义兜底", "正文以知识解释、事实梳理或评论为主，未发现更具体的事件型必要条件",
                               _rx(r"数据|原因|影响|风险|意味着|表明|指出", text) or "正文知识陈述", [], "语义裁决")
        return type_result("T25", "C-G01/T25", "内容过短且没有足够事件语义，暂不能稳定分类", "必要条件不足", [], "信息不足")

    precedence = ["T01", "T03", "T04", "T21", "T20", "T19", "T18", "T13", "T14", "T06", "T02",
                  "T05", "T07", "T10", "T08", "T09", "T12", "T17", "T16", "T15", "T11", "T24", "T22", "T23"]
    # 2026-09-18 复核补丁（C-T12 主事件锚定）：证据命中标题的候选优先于只由正文后段
    # （尾部栏目/推广/日报其他资讯）支撑的候选，防止杂质把主类型拉偏。
    def _title_anchored(chk):
        ev_terms = [t for t in re.split(r"＋|、|\|", chk.get("evidence", "")) if len(t.strip()) >= 2]
        return any(t in title for t in ev_terms)
    anchored = [x for x in checks if _title_anchored(x)]
    # 2026-09-18 复核补丁（C-T13 终选补强）：所有候选都只由正文后段（杂质）支撑、而标题
    # 本身写着设施/装备阶段跃迁（并网/投运/开工/纪录等）时，合成题名锚定的 T08 事件型判定，
    # 不让尾部栏目/往期回顾里的活动、融资词决定主类型。发布/推出/上市类词留给 T09/T11 分支。
    if not anchored:
        infra_event = _rx(r"开工|奠基|建成|投产|并网|投运|竣工|封顶|扩容|扩建|交付|量产|破纪录|世界纪录|"
                          r"商业化运营|商业运营|正式运营|全流程贯通|"
                          r"begins?|starts?|breaks?\s+ground|commissioned|comes?\s+online|record", title)
        if infra_event and all(x["tid"] not in ("T08", "T09", "T10", "T07") for x in checks):
            checks.append({"tid": "T08", "rule": "C-G02/C-T13",
                           "reason": "标题主事件是设施/装备的阶段状态跃迁；正文后段杂质不得覆盖题名事件",
                           "evidence": infra_event, "certainty": "规则裁决"})
            anchored = [x for x in checks if _title_anchored(x)]
    # 2026-09-19 v1.03（C-T13 补充）：标题党（如“废气变暖气！”）把阶段跃迁写在正文首段——
    # 「我国/全球首个＋投产/投运/建成＋具名主体」是首段主事件，不是尾部杂质，合成 T08。
    if not anchored:
        first_lead = re.search(r"(?:我国|国内|全球|世界)(?:首个|首次|首套|首创)[^\n]{0,80}?"
                               r"(?:投产|投运|建成|并网|运行)", body[:1400], re.I)
        named_actor = re.search(r"(?:院|公司|集团|大学|研究所|分公司|学会|协会|专委会|企业|工厂|部门)", body[:1400])
        if first_lead and named_actor and all(x["tid"] not in ("T08", "T10") for x in checks):
            checks.append({"tid": "T08", "rule": "C-G02/C-T13-首段跃迁",
                           "reason": "标题为科普/悬念式表达，正文首段锚定『首个＋投产/投运』具名项目主事件；主事件取首段而非标题修辞",
                           "evidence": re.sub(r"\s+", " ", first_lead.group(0))[:40], "certainty": "规则裁决"})
            anchored = [x for x in checks if x["tid"] == "T08"]
    chosen = min(anchored if anchored else checks, key=lambda x: precedence.index(x["tid"]))
    alternatives = [x["tid"] for x in checks if x["tid"] != chosen["tid"]]
    known_boundary = chosen["tid"] in {"T01", "T19", "T18", "T21", "T20", "T06", "T02"}
    if alternatives and known_boundary:
        certainty = "规则裁决"
        reason = chosen["reason"] + "；按跨类型证据优先级覆盖 " + "、".join(alternatives[:4])
    elif len(alternatives) >= 2:
        certainty = "语义裁决"
        reason = chosen["reason"] + "；按标题主事件确定主类型，附加事件记录为：" + "、".join(alternatives[:4])
    else:
        certainty = chosen["certainty"]
        reason = chosen["reason"]
    return type_result(chosen["tid"], chosen["rule"], reason, chosen["evidence"], alternatives, certainty)


def type_result(tid, rule, reason, evidence, alternatives, confidence):
    t = TYPE_BY_ID[tid]
    return {
        "tid": tid, "name": t["name"], "label": f"{tid} {t['name']}", "rule": rule,
        "reason": reason, "evidence": evidence, "alternatives": _uniq(alternatives),
        "confidence": confidence, "family": t.get("families", [""])[0] if t.get("families") else "",
        "card": base.CARD_OF_TYPE.get(tid) or {"T15": "card_market"}.get(tid),
    }


def _score_support(item, decision):
    """仅为 02 新闻价值评分卡提供事实特征；不参与领域选择。"""
    chosen = next((c for c in decision["candidates"] if decision["primary"] is c["dom"]), None)
    if not chosen:
        return {"title": 0, "body": 0, "actor": 0, "metric": 0, "route": 0,
                "core_title_n": 0, "core_body_n": 0, "core_hits": [], "ext_hits": [],
                "actor_hits": [], "metric_hit": "", "route_hit": ""}
    metric = 15 if chosen["metric"] else 0
    return {
        "title": 40 if chosen["title_object"] else 0,
        "body": 18 if chosen["body_object"] else 0,
        "actor": 15 if chosen["actor"] else 0,
        "metric": metric,
        "route": 40 if chosen["route"] else 0,
        "core_title_n": 2 if chosen["title_object"] else 0,
        "core_body_n": 2 if chosen["body_object"] else 0,
        "core_hits": chosen["terms"][:6], "ext_hits": [], "actor_hits": chosen["actor"],
        "metric_hit": ("数值＋领域单位(" + "、".join(chosen["metric"]) + ")") if metric else "",
        "route_hit": chosen["route"],
    }


ROUTE_PATTERNS = {
    "D01": [(r"TOPCon|HJT|BC电池|背接触|晶硅", 0), (r"钙钛矿|perovskite|叠层", 1), (r"OPV|CIGS|CdTe", 2)],
    "D02": [(r"液态|高镍|硅碳", 0), (r"固态|硫化物|氧化物电解质", 1), (r"锂金属|锂硫", 2)],
    "D03": [(r"锂电储能", 0), (r"液流电池", 1), (r"储热|长时储能|LDES|新构型", 2)],
    "D05": [(r"碱性电解|AWE", 0), (r"PEM.{0,8}电解|质子交换膜电解", 1), (r"SOEC|固体氧化物电解", 2), (r"绿氨|绿甲醇", 3)],
    "D06": [(r"陆上风电|近海风电", 0), (r"深远海|漂浮式|浮式|1[5-9]\s*MW|[2-9]\d\s*MW", 1)],
    "D07": [(r"华龙一号|三代核电|三代\+", 0), (r"SMR|小型模块化|小堆", 1), (r"聚变|托卡马克|EAST", 2)],
    "D08": [(r"传统.{0,5}CAES|补燃", 0), (r"AA-CAES|先进绝热|非补燃", 1)],
    "D09": [(r"废钢.{0,5}EAF|电弧炉", 0), (r"氢冶金|H2-DRI|直接还原铁|DRI", 1), (r"高炉富氢", 2)],
    "D10": [(r"替代燃料|熟料替代", 0), (r"水泥窑.{0,8}CCUS|水泥.{0,8}碳捕集", 1)],
    "D11": [(r"掺氨", 0), (r"掺氢|富氢燃烧", 1), (r"灵活性改造", 2)],
    "D12": [(r"胺法|点源捕集", 0), (r"\bDAC\b|直接空气捕集", 1), (r"CO2RR|二氧化碳电还原|电催化", 2),
            (r"\bMOF\b|金属有机框架", 3), (r"矿化|BECCS", 4)],
}

ROUTE_TRL_OVERRIDES = {
    ("D03", "储热/新构型长时"): "5-7",
    ("D05", "绿氨/绿甲醇项目"): "5-7",
    ("D07", "聚变(托卡马克/EAST 等)"): "2-4",
    ("D10", "水泥窑 CCUS"): "5-7",
    ("D12", "DAC"): "5-7",
}


def _route_rows(dom):
    if dom["id"] in CONFIRMED_META:
        defaults = base.D["trl_framework"].get("domain_defaults", [])
        row = next((x for x in defaults if x.get("domain_id") == dom["id"]), {})
        return [(x.get("route", ""), x.get("trl", ""), x.get("basis", "")) for x in row.get("routes", [])]
    return [tuple(x[:3]) for x in EXPANDED_META.get(dom["no"], {}).get("trl_routes", [])]


def _band_midpoint(band):
    nums = [int(x) for x in re.findall(r"\d+", str(band))]
    if not nums:
        return None
    return float(nums[0]) if len(nums) == 1 else (nums[0] + nums[1]) / 2


def _trl_weight(trl):
    if trl is None:
        return 1.0
    lo, hi = int(trl), min(9, int(trl) + 1)
    if lo == hi or trl == lo:
        return base.TRL_W[lo]
    return round(base.TRL_W[lo] + (base.TRL_W[hi] - base.TRL_W[lo]) * (trl - lo), 3)


def _route_frontier(item, dom):
    """S3：只按技术路线前沿确定 TRL；新闻事件阶段不替代路线成熟度。"""
    rows = _route_rows(dom)
    text = item["title"] + "\n" + item["body"][:1800]
    # 2026-09-18 复核补丁：不再取“首个命中”，而是在命中的路线中取最专属的一条；
    # 题名命中的路线优先于仅在正文背景出现的路线（如『钙钛矿/TOPCon叠层』归钙钛矿叠层路线，
    # 不被泛晶硅/TOPCon 词抢占成熟度权重）。
    hit_rows = []
    for pat, idx in ROUTE_PATTERNS.get(dom["no"], []):
        if idx < len(rows) and re.search(pat, text, re.I):
            hit_rows.append((idx, bool(re.search(pat, item["title"], re.I)), rows[idx]))
    selected = None
    if hit_rows:
        title_hits = [h for h in hit_rows if h[1]] or hit_rows
        selected = max(title_hits, key=lambda h: h[0])[2]
    if selected is None:
        # 扩展域用路线名称中的专属片段定位；未定位时遵循机制表取本域路线带中位数。
        stop = {"路线", "项目", "系统", "装置", "成熟", "示范", "主流", "传统", "新型", "其他"}
        for row in rows:
            terms = [x for x in re.findall(r"[A-Za-z0-9+.-]{2,}|[\u4e00-\u9fff]{2,}", row[0]) if x not in stop]
            if any(re.search(re.escape(x), text, re.I) for x in terms):
                selected = row
                break
    source = "命中技术路线"
    if selected:
        route, band, basis = selected
    elif rows:
        mids = sorted(x for x in (_band_midpoint(r[1]) for r in rows) if x is not None)
        mid = mids[len(mids) // 2]
        route, band, basis = "未定位具体路线（采用领域默认）", f"TRL {mid:g}", "机制表：无路线时取领域路线带中位数"
        return {"route": route, "band": band, "trl": mid, "weight": _trl_weight(mid), "basis": basis, "source": "领域默认"}
    else:
        return {"route": "扩展域通用路线", "band": "TRL 5", "trl": 5.0, "weight": _trl_weight(5.0),
                "basis": "新增/语义域采用中性TRL基准；类型卡证据决定价值，不以参数缺失降分", "source": "通用机制"}
    band = ROUTE_TRL_OVERRIDES.get((dom["no"], route), band)
    mid = _band_midpoint(band)
    return {"route": route, "band": "TRL " + str(band).replace("TRL", "").strip(), "trl": mid,
            "weight": _trl_weight(mid), "basis": basis, "source": source}


def _evidence_level(item):
    text = item.get("meta", "") + " " + item["title"] + " " + item["body"][:500]
    # 2026-09-24 v1.10（C-T16）：非文献源的 DOI 是引用线索不是原始载体——E1 收窄为 literature 源；
    # wechat/news 带 DOI 字段的报道按 E2 可溯源二手来源（DOI 可回查原文，仍高于单一媒体转载）。
    if item["src"] == "literature":
        return "E1", "论文/DOI 原始载体"
    if item.get("doi"):
        return "E2", "报道引用论文 DOI（二手可溯源）"
    if re.search(r"政府|发改委|能源局|工信部|财政部|生态环境部|委员会|交易所|公司公告|官网|官方", text, re.I):
        return "E1", "官方或监管原始载体"
    if re.search(r"大学|研究院|研究所|实验室|协会|学会|检测中心|TÜV|SGS|UL|Reuters|彭博", text, re.I):
        return "E2", "权威机构或独立专业来源"
    return "E3", "单一媒体/转载来源"


def _strictify_dimensions(dims, text):
    """数值只有在可比较口径成立时才可进入基线/突破档，避免把“有数字”当“高价值”。"""
    comparison = bool(re.search(r"同比|环比|相较|相比|高于|低于|提升|降低|减少|增加|基线|对照|benchmark|versus|\bvs\b", text, re.I))
    adjusted = []
    for name, got, mx, note in dims:
        if name == "性能×域阈值" and ("达域基线" in note or "突破档" in note) and not comparison:
            got = min(got, 8)
            note = "有量化值，但未建立同路线、同口径基线比较；按不可比档，不推定达基线/突破"
        adjusted.append([name, got, mx, note])
    return adjusted


def _band_of(value):
    if value is None:
        return "未评分"
    if value >= 75:
        return "高"
    if value >= 55:
        return "中"
    return "低"


def _score_by_mechanism(item, typ, dom, support):
    """严格执行 02 机制表 S1-S8；不反向影响语义分类。"""
    audit = [
        ["S1", "技术领域", f"{dom['no']} {dom['name']}（严格语义裁决，不计算D分）"],
        ["S2", "新闻类型", f"{typ['label']}（严格语义裁决，不计算T分）"],
    ]
    quality = item.get("content_quality", "")
    limited_evidence = quality in {"empty", "digest", "preview"} or not item["body"].strip()

    route = _route_frontier(item, dom)
    evidence_level, evidence_note = _evidence_level(item)
    audit.append(["S3", "路线TRL", f"{route['route']}；{route['band']}；w={route['weight']:.3f}；{route['source']}"])

    if not typ.get("card"):
        # 机制表未配置专卡时直接使用通用技术知识卡，保证评分不中断。
        typ = dict(typ)
        typ["card"] = "card_tech"
        audit.append(["S3b", "评分卡兜底", "类型无专属卡，按通用技术知识卡直接完成评分"])

    # 合作与人才此前复用了采购/组织卡，容易把普通签约和招聘抬成高分。这里使用专属机制。
    if typ["tid"] in {"T12", "T21"}:
        text = item["title"] + "\n" + item["body"][:2200]
        if typ["tid"] == "T12":
            dims = [
                ["合作约束力", 20 if re.search(r"正式签署|签署.{0,8}协议|合资|共同投资", text) else 10, 25, "正式协议高于意向表述"],
                ["资源承诺", 20 if re.search(r"金额|亿元|产线|项目落地|采购|订单|股权|投资", text) else 6, 25, "有资金、订单或产线承诺才进入高档"],
                ["技术实证", 22 if re.search(r"已完成|已验证|已投产|已交付|运行数据|客户验证", text) else 5, 25, "未来计划不等于已经验证"],
                ["领域相关性", 18 if support.get("title", 0) else 10, 25, "按主技术对象相关性"],
            ]
            cap = None if dims[1][1] >= 20 and dims[2][1] >= 22 else 54
        else:
            dims = [
                ["人才层级", 25 if re.search(r"院士|首席科学家|创始人|核心团队|领军人才", text) else 10, 30, "关键带头人或成建制团队才高"],
                ["能力增量", 25 if re.search(r"组建.{0,8}团队|研发中心|实验室|整体加盟|团队加入", text) else 8, 30, "一般岗位招聘不等于能力已形成"],
                ["规模与落实", 20 if re.search(r"\d+\s*(?:人|名)|团队|到岗|任命", text) else 6, 20, "人数或到岗状态"],
                ["领域关键性", 20 if support.get("title", 0) else 10, 20, "是否直接补强核心技术能力"],
            ]
            cap = 54 if re.search(r"招聘|岗位|简历投递|任职要求|招生|本科|硕士|研究生", text) and not re.search(r"任命|到岗|团队加入", text) else None
        raw = sum(d[1] for d in dims)
        value = float(min(raw, cap) if cap is not None else raw)
        band = _band_of(value)
        gates = [f"普通{('合作' if typ['tid']=='T12' else '招聘')}事件封顶{cap}"] if cap is not None else []
        audit.extend([
            ["S4", "专项维度", f"Σ={raw:g}；" + "；".join(f"{d[0]} {d[1]}/{d[2]}" for d in dims)],
            ["S5", "TRL加权", "组织与合作类不乘TRL"], ["S6", "Gate", "；".join(gates) if gates else "未触发封顶"],
            ["S7", "记录合成", "主事件单独评分；附加技术背景不另行抬分"], ["S8", "最终档位", f"{value:g} → {band}"],
        ])
        return {"value": value, "valueDisplay": f"{value:g}", "raw": raw, "gated": value, "band": band,
                "dimensions": dims, "trlInfo": route, "weight": 1.0, "cap": cap,
                "evidenceLevel": evidence_level, "evidenceNote": evidence_note, "gateActions": gates,
                "missingEvidence": [], "scoreStatus": "已评分", "audit": audit}

    # 技术投入品发布不能只按终端装备的“参数/容量”卡判断。具名材料产品若同时说明
    # 目标体系、作用机理和制造价值，即使没有终端设备容量，也具有可执行的产业情报价值。
    if typ["tid"] == "T09":
        text = item["title"] + "\n" + item["body"][:2600]
        material_product = bool(re.search(r"粘结剂|电解质|电极材料|隔膜|催化剂|添加剂|binder|electrolyte|cathode|anode", text, re.I))
        named_release = bool(re.search(r"发布|推出|上市|launch|unveil|release", item["title"], re.I) and
                             re.search(r"[A-Za-z][A-Za-z0-9-]{2,}(?:\s+[A-Z][A-Z0-9-]+)?", item["title"]))
        target_system = bool(re.search(r"固态电池|硫化物|锂电|钠电|光伏|氢能|燃料电池|solid-state|battery|solar|hydrogen", text, re.I))
        mechanism = bool(re.search(r"相比|相较|可降低|有助于|适用于|稳定性|一致性|可制造性|无需|不再依赖|compared|improv|reduce|stability", text, re.I))
        if material_product and named_release and target_system and len(item["body"]) >= 300:
            dims = [
                ["商业化状态", 22, 25, "具名产品已发布，区别于概念或研发预告"],
                ["目标体系明确度", 24, 25, "明确材料功能、目标电池体系和使用环节"],
                ["机理与工艺价值", 18 if mechanism else 10, 25, "说明相容性、稳定性或制造流程价值"],
                ["信息完整性", 12, 25, "具名供应商、产品名、材料体系与应用场景齐全；暂缺第三方量化验证"],
            ]
            raw = sum(d[1] for d in dims)
            weight = route["weight"]
            value = round(raw * weight, 1)
            band = _band_of(value)
            audit.extend([
                ["S4", "技术投入品专项维度", f"Σ={raw:g}；" + "；".join(f"{d[0]} {d[1]}/{d[2]}" for d in dims)],
                ["S5", "TRL加权", f"{raw:g} × {weight:.3f} = {value:g}"],
                ["S6", "Gate", "缺少第三方量化验证仅体现在信息完整性维度，不否定其产业情报价值"],
                ["S7", "记录合成", "主事件为具名技术投入品发布；展会信息仅作场景背景"],
                ["S8", "最终档位", f"{value:g} → {band}"],
            ])
            return {"value": value, "valueDisplay": f"{value:g}", "raw": raw, "gated": raw, "band": band,
                    "dimensions": dims, "trlInfo": route, "weight": weight, "cap": None,
                    "evidenceLevel": evidence_level, "evidenceNote": evidence_note, "gateActions": [],
                    "missingEvidence": ["第三方量化验证"], "scoreStatus": "已评分", "audit": audit}

    # S-R01：报告类只给粗分档，禁止伪造精确点分。
    if typ["tid"] == "T02":
        text = item["title"] + "\n" + item["body"][:2500]
        method = bool(re.search(r"方法|口径|methodology|数据来源", text, re.I))
        sample = bool(re.search(r"样本|问卷|survey|sample|覆盖|国家|地区|企业", text, re.I))
        series = bool(re.search(r"连续第|第\d+次|年度|季度|月度|系列|同比|CAGR", text, re.I))
        if method and sample and series and evidence_level in {"E1", "E2"}:
            band, rng = "高", "75–89"
        elif method and sample:
            band, rng = "中", "55–74"
        else:
            band, rng = "低", "35–54"
        audit.extend([
            ["S4", "报告专项通道", f"方法={method}；样本/覆盖={sample}；连续性={series}；信源={evidence_level}"],
            ["S5", "TRL加权", "S-R01 报告通道不生成精确点分"], ["S6", "Gate", "仅输出粗分档"],
            ["S7", "记录合成", "单一报告事件"], ["S8", "最终档位", f"{band}（{rng}）"],
        ])
        missing = [n for n, ok in (("方法/口径", method), ("样本/覆盖", sample), ("连续序列", series)) if not ok]
        return {"value": None, "valueDisplay": rng, "raw": None, "gated": None, "band": band,
                "dimensions": [["报告专项通道", 0, 0, f"方法={method}；样本/覆盖={sample}；连续性={series}"]],
                "trlInfo": route, "weight": 1.0, "cap": None, "evidenceLevel": evidence_level,
                "gateActions": ["S-R01 仅粗分档"], "missingEvidence": missing,
                "scoreStatus": "区间评分", "audit": audit}

    card_trl = None if route["trl"] is None else max(1, min(9, int(route["trl"] + 0.5)))
    raw0, dims, _trl, base_weight, cap = base.score_card(item, typ["tid"], dom, support, trl_override=card_trl)
    dims = _strictify_dimensions(dims, item["title"] + "\n" + item["body"][:2500])

    # 已完成投产且披露合格产出、连续生产或稳定运行的事件，是产业化跨阶段事实，
    # 不能因为正文出现“突破/全球首套”就按宣传性主张封顶。
    text_full = item["title"] + "\n" + item["body"][:3200]
    verified_operation = typ["tid"] == "T10" and bool(
        re.search(r"投产|量产|商业运行|投入运行", item["title"], re.I) and
        re.search(r"产出合格产品|打通全流程|连续生产|稳定运行|一次开车成功", text_full, re.I)
    )
    if verified_operation:
        for d in dims:
            if d[0] == "良率/利用率/可靠性披露":
                d[1], d[3] = max(d[1], 8), "合格产出及全流程/稳定运行事实，按已验证可靠性档"
            elif d[0] == "运行时长/出货证据":
                d[1], d[3] = max(d[1], 10), "连续生产或打通全流程，强于单点开车时点"
            elif d[0] == "主体产线地位":
                d[1], d[3] = max(d[1], 8), "明确具名企业与产业化装置"

    # 全球/国际首个统一标准已经发布，影响强度不是“指导性吹风”。
    if typ["tid"] == "T20" and re.search(r"全球|国际", item["title"], re.I) and re.search(r"首个|首次", item["title"], re.I) and re.search(r"标准", item["title"], re.I):
        for d in dims:
            if d[0] == "影响强度":
                d[1], d[3] = max(d[1], 25), "全球/国际首个统一标准已发布，按正式规则高影响档"

    # 有独立机构验证的纪录级核心性能，需把指标与新颖性按机制表高档处理。
    record_validation = typ["tid"] == "T06" and bool(
        re.search(r"record|纪录|最高|achiev", text_full, re.I) and
        re.search(r"%|％|效率|efficien", text_full, re.I) and
        re.search(r"validated|certified|认证|验证|研究所|Institute|TÜV|SGS|UL", text_full, re.I)
    )
    # 2026-09-18 复核补丁（问题10）：题名锚定的『纪录+数值%』产品/验证事件（如叠层电池效率
    # 34.82% 世界纪录）按 S-V01 纪录口径对待——数值是事件本体载荷而非宣传背景，
    # 不得被正文宣传词（杂质）触发的 S-G03 封顶压成低档；证据层级维度照常计分。
    # 2026-09-19 v1.03：T08 项目类题名纪录（研制成功+效率%+刷新纪录）同口径。
    title_record_metric = typ["tid"] in {"T06", "T07", "T08", "T09", "T10"} and bool(
        re.search(r"纪录|record", item["title"], re.I)
        and re.search(r"\d+(?:\.\d+)?\s*[%％]", item["title"]))
    if title_record_metric:
        record_validation = True
    # 2026-09-19 v1.03（S-F01 首创认证通道）：『我国/全球首个＋投产/认证/标准』是产业化首证事实
    # （如首个CO2地热项目投产、奶牛场沼气制SAF达ASTM标准），按纪录口径计分，不受宣传词封顶。
    # 2026-09-20 v1.04（M3）：与 S10 层同口径——首创词补首座、落地族补投运/商业运营/全流程
    # 贯通/倒送电、UL 等拉丁认证词加词边界；题名含基金/申报指南/大会/演讲语境或在建/将建
    # 事件时不触发（企业宣传 boilerplate 与将建工程不是技术首证事实）。
    _pr_excluded = bool(FIRST_PR_EXCLUDE_R.search(item["title"]))
    _future_proj = bool(FUTURE_PROJECT_R.search(item["title"]) and not LANDED_IN_TITLE_R.search(item["title"]))
    # 2026-09-23 v1.08（W1/W2）：将来时里程碑/部署不按首证计分——预计10月转入商业运营、
    # 下半年将在…部署是计划，事件未发生（与 S10 层 S-A05 同口径）。
    _future_plan = bool(FUTURE_LANDED_R.search(item["title"]) or FUTURE_DEPLOY_R.search(item["title"]))
    first_verified = bool(
        not _pr_excluded and not _future_proj and not _future_plan
        and FIRST_VERIFIED_R_V104.search(item["title"] + "\n" + item["body"][:900])
        and FIRST_EVIDENCE_R_V104.search(item["title"] + "\n" + item["body"][:1200]))
    if first_verified:
        record_validation = True
        for d in dims:
            if d[0] in {"阶段跃迁", "工程确定性"}:
                d[1], d[3] = max(d[1], 18), "『首个＋认证/投产』首证事实，按跨阶段产业化档"
            elif d[0] in {"新颖性/机理", "影响强度"}:
                d[1], d[3] = max(d[1], 18), "全球/国内首个并经第三方或标准验证，按显著新颖档"
    if record_validation:
        for d in dims:
            if d[0] in {"指标表现×域基线", "性能×域阈值"}:
                d[1], d[3] = max(d[1], 25), "纪录级核心指标且由独立机构验证，按突破档"
            elif d[0] == "新颖性/机理":
                d[1], d[3] = max(d[1], 20), "刷新同路线纪录，按显著新颖性档"
    raw = sum(d[1] for d in dims)
    gates = []
    if cap is not None:
        gates.append(f"评分卡Gate封顶{cap}")
    text = item["title"] + "\n" + item["body"][:1800]
    # 2026-09-20 v1.04（M7）：题名工程里程碑事实（倒送电/并网成功/全流程贯通/商业化运营/
    # 一次性成功）是事件本体载荷，同 S-V01 纪录口径豁免 S-G03 宣传封顶（『能储一号』
    # 350MW 压气储能倒送电一次性成功不得因正文『世界级』字样封顶54）。
    # 2026-09-23 v1.08（W1）：将来时里程碑（预计10月转入商业运营）不豁免 S-G03——S-F02 同步不触发。
    title_stage_fact = bool(MILESTONE_TITLE_R.search(item["title"]) and not FUTURE_LANDED_R.search(item["title"]))
    if (not verified_operation and not first_verified and not title_stage_fact
            and re.search(r"领先|突破|颠覆|革命性|世界级|行业第一", text, re.I)
            and not title_record_metric
            and not re.search(r"第三方|测试|报告|方法|样本|对照|基准", text, re.I)):
        cap = min(cap or 100, 54)
        gates.append("S-G03 宣传性数字/主张缺少验证，封顶54")
    elif title_record_metric:
        gates.append("S-G03 豁免：题名『纪录+数值%』即事件本体载荷（S-V01 纪录口径），正文宣传词只作背景不封顶")
    elif title_stage_fact:
        gates.append("S-G03 豁免：题名工程里程碑事实（倒送电/并网成功/全流程贯通/商业化运营）即事件本体载荷（S-F02 口径），宣传词只作背景不封顶")
    elif first_verified:
        gates.append("S-G03 豁免：『首个＋认证/标准/投产』为首证事实（S-F01 口径），宣传词只作背景不封顶")
    if limited_evidence:
        title_self_sufficient = typ["tid"] in {"T19", "T20", "T13", "T14", "T18"} and bool(re.search(r"批准|发布|实施|生效|融资|收购|中标|招标|亿元|万美元|欧元", item["title"], re.I))
        cap = min(cap or 100, 74 if title_self_sufficient else 54)
        gates.append(f"S-G01 仅标题/摘要证据，封顶{cap}并保留低证据标签")
    gated = min(raw, cap) if cap is not None else raw
    weighted_card = "是" in str(base.CARDS[typ["card"]].get("trl_weighted", ""))
    weight = route["weight"] if weighted_card else 1.0
    value = round(gated * weight, 1)
    # 2026-09-19 v1.03（S-V02 信源提示分）：专业编辑信源（REAI Lab、国际能源小数据等）
    # 对证据完整性有正向提示，+5（草案 null 待回测），只加分数不改档位口径。
    source_hint = next((a for a in BAND_POLICY_V103["source_hint_accounts"] if a in str(item.get("meta") or "")), "")
    if source_hint:
        value = round(min(100.0, value + BAND_POLICY_V103["source_hint_bonus"]), 1)
        gates.append(f"S-V02 信源提示：{source_hint} +{BAND_POLICY_V103['source_hint_bonus']}（专业编辑信源，草案常数）")
    if evidence_level == "E3" and value > 74 and not verified_operation:
        value = 74.0
        gates.append("S-G04 E3单一来源高结论封顶74，待E1/E2复核")
    band = _band_of(value)
    missing = _uniq([d[0] for d in dims if re.search(r"未说明|无数值|未披露|不可比|无口径|缺失|未知", str(d[3]))])
    audit.extend([
        ["S4", "原始维度", f"Σ={raw:g}；" + "；".join(f"{d[0]} {d[1]}/{d[2]}" for d in dims if d[2])],
        ["S5", "TRL加权", f"{gated:g} × {weight:.3f} = {round(gated * weight, 1):g}" if weighted_card else f"C组卡不乘TRL，保持 {gated:g}"],
        ["S6", "Gate", "；".join(gates) if gates else "未触发额外封顶"],
        ["S7", "记录合成", "当前记录提取为单一事件；无第二/第三异质事件加成"],
        ["S8", "最终档位", f"{value:g} → {band}"],
    ])
    return {"value": value, "valueDisplay": f"{value:g}", "raw": raw, "gated": gated, "band": band,
            "dimensions": dims, "trlInfo": route, "weight": weight, "cap": cap,
            "evidenceLevel": evidence_level, "evidenceNote": evidence_note, "gateActions": gates,
            "missingEvidence": missing, "scoreStatus": "已评分", "audit": audit}


def _unregistered_domain_score(item, typ, dom, decision):
    """新增/语义域直接使用通用类型卡评分；参数缺失不再形成待办状态。"""
    text = item["title"] + "\n" + item["body"][:1800]
    terms = decision.get("terms", [])
    title_hit = any(re.search(re.escape(x), item["title"], re.I) for x in terms if x)
    body_hit = any(re.search(re.escape(x), item["body"][:1800], re.I) for x in terms if x)
    metric_hit = bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|％|MW|GW|GWh|MWh|亿元|万美元|欧元|倍|人|项|条)", text, re.I))
    support = {"title": 40 if title_hit else 28, "body": 18 if body_hit else 6, "actor": 0,
               "metric": 15 if metric_hit else 0, "route": 0, "core_title_n": 2 if title_hit else 1,
               "core_body_n": 2 if body_hit else 0, "core_hits": terms[:6], "ext_hits": [],
               "actor_hits": [], "metric_hit": "通用量化证据" if metric_hit else "", "route_hit": ""}
    return _score_by_mechanism(item, typ, dom, support)


def _norm_title(s):
    return re.sub(r"[\W_]+", "", (s or "").lower(), flags=re.U)


OUTSIDE_TOPIC_PATTERNS = [
    ("生命医学与农业食品", r"genom|protein|HIV|virus|cancer|disease|medical|clinical|health|neuron|microb|bacter|"
                         r"crop|food|agricultur|skeleton|mortality|生命|医学|疾病|健康|基因|蛋白|细胞|病毒|癌|神经|农业|食品|作物|生物"),
    ("基础物理化学与一般材料", r"cataly|synthesis|molecular|quantum|particle|gauge|mathemat|crystal|polymer|membrane|"
                              r"chemical|reaction|spectroscop|electron|proton|spin|mechanics|dielectric|"
                              r"催化|合成|分子|量子|粒子|理论|数学|晶体|聚合物|化学|反应|电子|质子|力学|介电"),
    ("气候环境与地球生态", r"climate|weather|monsoon|rainfall|forest|soil|ocean|pollution|ecolog|archaeolog|geolog|"
                          r"earthquake|drought|flood|ozone|气候|天气|降雨|森林|土壤|海洋|污染|生态|考古|地质|地震|干旱|洪水|臭氧"),
    ("宏观能源与碳议题", r"energy|electricity|renewable|decarbon|emission|carbon|能源|电力|新能源|可再生|碳排|脱碳|低碳"),
    ("经济商业政策与社会", r"market|price|trade|finance|economic|policy|company|business|startup|funding|politic|wealth|inequality|"
                          r"市场|价格|贸易|金融|经济|政策|企业|公司|融资|政治|社会|教育|法律"),
    ("数字软件与信息安全", r"software|internet|cyber|platform|algorithm|computer|smartphone|privacy|"
                          r"游戏|软件|互联网|网络安全|数据平台|算法|计算机|手机|隐私"),
    ("交通航天国防及其他工业", r"vehicle|automotive|aircraft|ship|military|defen[cs]e|drone|transport|"
                              r"汽车|航空|航天|船舶|军事|国防|无人机|交通"),
]


def _outside_analysis(item, typ):
    """把“域外”拆成可复核的结构原因与内容主题；不参与归域本身。"""
    quality = item.get("content_quality", "")
    if re.search(r"影响因子|期刊分区|征稿|审稿周期|投稿链接|APC|CiteScore", item["title"] + "\n" + item["body"][:1600], re.I):
        reason = "O9 期刊运营与征稿信息，非技术内容"
        detail = "主事件是期刊影响因子、分区、稿件类型、审稿或投稿信息；未报道具体技术研究、产品、工程或政策对象，因此明确判为域外。"
    elif quality in {"empty", "digest"} or not item["body"].strip():
        reason = "O1 正文不足且标题无目标技术对象"
        detail = "正文为空或仅为摘要/合辑，标题也未出现零碳、AI或通用技术语义树中的明确对象。"
    elif typ["tid"] == "T01":
        reason = "O2 论文对象未落入当前行业图景"
        detail = "论文载体成立，但题名与摘要的主要研究对象没有落入零碳、AI或通用技术的已登记语义叶。"
    elif typ["tid"] == "T25":
        reason = "O3 类型和技术对象均不足"
        detail = "既未识别出满足必要条件的新闻事件类型，也未识别出明确目标技术对象。"
    elif typ["tid"] in {"T11", "T12", "T13", "T14", "T16", "T17", "T18"}:
        reason = "O4 商业资本或市场事件未绑定技术对象"
        detail = "交易、合作、市场、供应链或采购事件可以识别，但主对象是公司、金额或市场，不是已登记技术对象。"
    elif typ["tid"] in {"T19", "T20"}:
        reason = "O5 政策标准未绑定技术对象"
        detail = "政策或标准事件成立，但作用对象停留在宏观制度、地区或一般行业层面。"
    elif typ["tid"] in {"T21", "T22", "T23", "T24"}:
        reason = "O6 软信息未绑定技术对象"
        detail = "观点、分析、会议或人才信息成立，但没有明确落到语义树中的目标技术对象。"
    elif typ["tid"] in {"T05", "T06", "T07", "T08", "T09", "T10"}:
        reason = "O7 研发产品或工程事件缺少登记技术对象"
        detail = "研发、评测、验证、项目、产品或运行事件成立，但具体对象未进入当前语义树。"
    else:
        reason = "O8 其他事件未绑定技术对象"
        detail = "新闻事件有一定结构，但没有足够语义证据归入任何登记技术域。"

    title = item["title"]
    topic = "其他未登记主题或标题过泛"
    for label, pattern in OUTSIDE_TOPIC_PATTERNS:
        if re.search(pattern, title, re.I):
            topic = label
            break
    return reason, detail, topic


def _summary_counts(items, key):
    counts = {}
    for x in items:
        value = x.get(key) or "未标注"
        counts[value] = counts.get(value, 0) + 1
    total = len(items) or 1
    return [{"name": name, "count": n, "pct": round(n * 100 / total, 1)}
            for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


# ============ 2026-09-18 v1.02：大模型语义判定合并 + 优先级分层（运行层） ============
# 数据契约见《分类基准与AI执行约束_20260918.md》§输出契约：
#   llm_semantic_decisions.json = {url: {domain_path, domain_no, type_id, terms[], alternatives[],
#                                        reason, confidence}}
# 合并原则：LLM 语义裁决覆盖规则层的域/类型；规则层结果保留为参考痕迹。
# 优先级分层只改阅读顺序与档位上限，不改写分数本身（02 工作簿《v1.02优先级分层》公式直译）。

LLM_DECISIONS_PATH = os.path.join(HERE, "llm_semantic_decisions.json")


def _load_llm_decisions():
    if not os.path.exists(LLM_DECISIONS_PATH):
        return {}
    try:
        with open(LLM_DECISIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[warn] llm_semantic_decisions.json 解析失败，忽略：{e}")
        return {}
    if isinstance(data, dict) and isinstance(data.get("decisions"), (list, dict)):
        data = data["decisions"]
    if isinstance(data, list):
        data = {d.get("url"): d for d in data if isinstance(d, dict) and d.get("url")}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


_LLM_CONF_MAP = {"high": "明确", "medium": "可判", "low": "低信"}


def _llm_override_dom(dec, rule_dom):
    """按 LLM 决策构造与规则层同构的领域判定对象；无法解析时返回 None（回退规则层）。"""
    no = str(dec.get("domain_no") or "").strip().upper()
    path = str(dec.get("domain_path") or "").strip()
    # 2026-09-21 v2 落地修复：此前『path=域外 且 no 为空』提前 return None，导致下方域外分支
    # 永不可达（域外裁决 domain_no 恒为空）——LLM 域外改判从不生效（06-24 批 Surface 实证）。
    # 现仅真正空裁决（path/no 双空）才回退规则层；域外裁决走下方分支改判域外。
    if not path and not no:
        return None
    conf = _LLM_CONF_MAP.get(str(dec.get("confidence", "")).lower(), "可判")
    rule_ref = rule_dom.get("rule", "") if isinstance(rule_dom, dict) else ""
    if path in ("域外", "OUT_OF_SCOPE"):
        return {
            "primary": None, "secondary": [], "disp": "域外", "confidence": conf,
            "rule": f"LLM语义/域外（规则层参考:{rule_ref}）",
            "reason": f"大模型语义判定为域外：{dec.get('reason', '')}",
            "terms": list(dec.get("terms") or []), "snippet": "", "label": "", "candidates": [],
        }
    if no in DOM_BY_NO:
        d = DOM_BY_NO[no]
        disp = "主域" if d.get("status") == "confirmed" else "主域(草案)"
        label = f"{d['no']} {d['name']}"
    else:
        # 基准树内语义叶/LLM 新判扩展域：按 path 尾段构造扩展叶，走通用类型卡评分。
        name = re.split(r"[|>]", path)[-1].strip() or path
        no = no or "LLM"
        d = {"no": no, "id": no, "name": name, "status": "extended",
             "core": [name], "ext": [], "actors": [], "units": []}
        disp, label = "主域(扩展)", f"{no} {name}"
    terms = _uniq([d["name"]] + [str(t) for t in (dec.get("terms") or []) if str(t).strip()])[:6]
    return {
        "primary": d, "secondary": [], "disp": disp, "confidence": conf,
        "rule": f"LLM语义（规则层参考:{rule_ref}）",
        "reason": f"大模型按两份基准 docx 语义判定：{dec.get('reason', '')}",
        "terms": terms, "snippet": _first_snippet(path, terms), "label": label,
        "candidates": [], "llm": True,
    }


def _llm_override_typ(dec, rule_typ):
    """按 LLM 决策构造类型判定对象；type_id 不在 T01–T25 时返回 None。"""
    tid = str(dec.get("type_id") or "").strip().upper()
    if tid not in TYPE_BY_ID:
        return None
    conf = _LLM_CONF_MAP.get(str(dec.get("confidence", "")).lower(), "可判")
    rule_ref = rule_typ.get("rule", "") if isinstance(rule_typ, dict) else ""
    reason = str(dec.get("reason") or "").strip() or "大模型按新闻类型语义基准判定"
    return type_result(
        tid, f"LLM语义/C-T参考（规则层参考:{rule_ref}）",
        f"大模型语义判定：{reason}", f"LLM：{reason}",
        list(dec.get("alternatives") or []), conf)


# ---- 优先级分层常数（镜像 score_data.PRIORITY_TIERS；单源在 score_data.py，此处只展开）----
_P0_GROUPS = PRIORITY_TIERS["domains_p0"]
P0_DOMAIN_NOS = set(_P0_GROUPS["电池族"] + _P0_GROUPS["能源族"] + _P0_GROUPS["零碳产业脱碳族"]
                    + PRIORITY_TIERS.get("domains_p0_v103_energy_extra", []))
TYPES_P0_NOS = set(PRIORITY_TIERS["types_p0_tech"])
TYPES_P2_NOS = set(PRIORITY_TIERS["types_p2_softinfo"])
TYPE_BAND_CAP = dict(PRIORITY_TIERS["type_band_cap"])  # {"T11": "中", "T13": "中", "T14": "中", "T24": "中"}
BAND_RANK = {"低": 0, "中": 1, "高": 2}
TIER_RANK = {"P0": 0, "P1": 1, "P2": 2}

# ---- 2026-09-24 v1.09：展示链路（《新闻类型展示分类.xlsx》用户 2026-09-24 指定结构）----
# 纯展示标注层：按最终类型 T01–T25 映射 展示大类/展示小类/归入大类（A 科研知识 / B 产业化主链 /
# C 企业支撑 / D 外部环境，见 02 机制表《大类与产业链导航》）。不参与 S1–S10 任何评分、档位、
# 优先级判定（用户口径："程序的输出结果包含展示的新闻类型，但不影响后台评分"）。
# 论文（T01）单列展示大类；小类=四分型逐条判定（用户 2026-09-24 追加口径：综述/研究型/分析类/
# 新闻·评论·观点 不得混在一起）——由 _paper_display_subtype 按题名证据级联判定，MAP 里为默认值。
# T24 会议=场合标签，展示挂"观点与交流"，发布物按实质归类由类型层负责。
DISPLAY_CHAIN_MAP = {
    "T01": ("论文", "研究型", "A"),
    "T02": ("新闻", "知识资产", "A"),
    "T03": ("新闻", "知识资产", "A"),
    "T04": ("新闻", "知识资产", "A"),
    "T05": ("新闻", "知识资产（计分走B链3工程示范）", "A"),
    "T06": ("新闻", "知识资产", "A"),
    "T07": ("新闻", "工程与产业化", "B(链2-5)"),
    "T08": ("新闻", "工程与产业化", "B(链2-5)"),
    "T09": ("新闻", "工程与产业化", "B(链2-5)"),
    "T10": ("新闻", "工程与产业化", "B(链2-5)"),
    "T11": ("新闻", "企业经营、合作与资本", "C"),
    "T12": ("新闻", "企业经营、合作与资本", "C"),
    "T13": ("新闻", "企业经营、合作与资本", "C"),
    "T14": ("新闻", "企业经营、合作与资本", "C"),
    "T15": ("新闻", "资源、市场与产业链", "C(卡待建)"),
    "T16": ("新闻", "资源、市场与产业链", "D"),
    "T17": ("新闻", "资源、市场与产业链", "B链6/C"),
    "T18": ("新闻", "资源、市场与产业链", "C"),
    "T19": ("新闻", "政策、法规与标准", "D"),
    "T20": ("新闻", "政策、法规与标准", "D"),
    "T21": ("新闻", "人才与组织动态", "C"),
    "T22": ("新闻", "观点与交流", "A"),
    "T23": ("新闻", "观点与交流（建模分析通道）", "A"),
    "T24": ("新闻", "观点与交流（场合标签）", "A"),
    "T25": ("待定", "信息不足", "—"),
}

# ---- v1.09 论文四分型（用户 2026-09-24 口径：四个小类逐条展开，不整体标注）----
# 确定性题名证据级联（纯展示，不进评分；与《新闻类型展示分类.xlsx》四小类逐字对齐）：
#   ① 非文献源（news/wechat）的 T01 = 论文报道/媒体解读稿 → 新闻/评论/观点
#      （全文转载特征除外：《刊名》文章/引用本文 → 仍按论文体裁判）；
#   ② 题名综述词（综述/研究进展/展望/review/perspective/primer/meta-analysis…）→ 综述；
#   ③ 题名评估分析词（技术经济/生命周期/碳足迹/情景/assessment/techno-economic/LCA…）→ 分析类；
#   ④ 默认 → 研究型。
PAPER_SUBTYPE_REVIEW_R = re.compile(
    r"综述|研究进展|进展与挑战|系统性回顾|研究展望|展望|路线图"
    r"|\b(reviews?|primer|advances|outlook|perspectives?|roadmap|survey|meta[- ]analys(?:is|es)|progress)\b",
    re.I)
PAPER_SUBTYPE_ANALYSIS_R = re.compile(
    r"技术经济|经济性分析|生命周期|碳足迹|水足迹|情景|影响评估|政策分析|市场分析|成本分析|评估|评价"
    r"|\b(assessments?|evaluations?|techno[- ]economic|life[- ]cycle|carbon footprint|water footprint"
    r"|scenarios?|forecasts?|LCA|TEA)\b",
    re.I)
PAPER_REPRINT_R = re.compile(r"《[^》]{2,20}》(?:文章|论文|全文)")


def _paper_display_subtype(src, title, body=""):
    """论文展示四分型：综述 / 研究型 / 分析类 / 新闻/评论/观点（纯展示层判定）。"""
    title = title or ""
    reprint = PAPER_REPRINT_R.search(title) or "引用本文" in (body or "")[:400]
    if src != "literature" and not reprint:
        return "新闻/评论/观点"
    if PAPER_SUBTYPE_REVIEW_R.search(title):
        return "综述"
    if PAPER_SUBTYPE_ANALYSIS_R.search(title):
        return "分析类"
    return "研究型"

# ---- 2026-09-19 v1.03：S10 档位政策层常数（单源 score_data.BAND_POLICY_V103，此处只展开）----
SOFT_LOW_TYPES = set(BAND_POLICY_V103["soft_low_types"])
PROC_LOW_TYPES = set(BAND_POLICY_V103["proc_low_types"])
AUTO_WHITELIST_R = re.compile("|".join(re.escape(x) for x in BAND_POLICY_V103["auto_whitelist"]), re.I)
BIO_HOTSPOT_R = re.compile("|".join(re.escape(x) for x in BAND_POLICY_V103["bio_hotspot"]), re.I)
BOTTLENECK_R = re.compile("|".join(re.escape(x) for x in BAND_POLICY_V103["bottleneck_words"]), re.I)
BOTTLENECK_DEG_R = re.compile(r"加剧|恶化|延长|翻倍|\d+\s*(?:年|月|周|%|％)|等\s*\d+\s*年|[达约]\s*\d+\s*(?:周|月)|倍", re.I)
NATIONAL_POLICY_R = re.compile("|".join(re.escape(x) for x in BAND_POLICY_V103["national_policy_words"]))
TOP_JOURNAL_R = re.compile(r"(?<![A-Za-z])(?:Nature|Science|Joule|Cell|PNAS)(?![A-Za-z])", re.I)
AUTO_CONTENT_R = re.compile(r"整车|车企|新车|车型|轿车|SUV|猎跑|猎装|轿跑|MPV|皮卡|4S店|经销商|试驾|车评|上市发布会", re.I)
AUTO_DOM_R = re.compile(r"陆路运输|整车制造|智能汽车|车联网|汽车", re.I)
BIO_DOM_R = re.compile(r"医学|生物医药|生物医学|药学|医疗|健康科学|基础学科", re.I)
FIRST_VERIFIED_R = re.compile(r"全球首创|世界首次|世界首个|我国首个|国内首个|首次实现|首套|刷新世界纪录|世界纪录", re.I)
FIRST_EVIDENCE_R = re.compile(r"认证|标准|ASTM|D7566|JET|TÜV|SGS|UL|第三方|验证|示范工程|正式投产|投产运行", re.I)
LANDED_FACT_R = re.compile(r"投产|建成|并网|投运|量产|交付|投运|正式运行", re.I)
FOCUS_EXTRA_R = re.compile(r"电池|储能|能源|氢|电网|碳|脱碳|零碳|AI|智能|半导体|芯片|光电|算力|数据中心|"
                           r"光伏|风电|水电|核电|聚变|生物质|钢铁|化工|水泥|铝|地热|CCUS|具身|机器人", re.I)

# ---- 2026-09-20 v1.04：第 4 轮反馈（12 条）S10 修订常数（单源 score_data.BAND_POLICY_V104）----
# M3：S-F01 首创词/落地族扩展 + 题名语境排除 + 在建防护（题名级判定，S10 与评分层共用）。
FIRST_VERIFIED_R_V104 = re.compile(FIRST_VERIFIED_R.pattern + "|" + "|".join(
    re.escape(x) for x in BAND_POLICY_V104["first_verified_extra"]), re.I)
FIRST_EVIDENCE_R_V104 = re.compile(r"认证|标准|ASTM|D7566|JET|TÜV|SGS|\bUL\b|第三方|验证|示范工程|示范项目|"
                                   r"正式投产|投产运行|投产|" + "|".join(re.escape(x) for x in
                                   BAND_POLICY_V104["first_evidence_extra"]), re.I)
FIRST_PR_EXCLUDE_R = re.compile("|".join(re.escape(x) for x in BAND_POLICY_V104["first_pr_exclude"]))
# 2026-09-20 测试轮（06-24 批次）补 加快建设/加速建设/建设中/正在建设：
# 『大别山空气充电宝加快建设』题名是进行态建设报道，正文首座+示范工程不得借 S-F01 抬高。
FUTURE_PROJECT_R = re.compile(r"推进建设|将建|拟建|计划建设|计划建|开工|奠基|启动建设|加快建设|加速建设|建设中|正在建设|推进$", re.I)
LANDED_IN_TITLE_R = re.compile(r"投产|投运|建成|并网|运营|交付|量产", re.I)
# M2：招投标公告词（题名锚定）。
BID_ANNOUNCE_R = re.compile("|".join(re.escape(x) for x in BAND_POLICY_V104["bid_announce_words"]))
# M5：省级地名 / 国家级主体词 / 地方申报事件词。
PROVINCE_R = re.compile("|".join(re.escape(x) for x in BAND_POLICY_V104["province_names"]))
NATIONAL_BODY_R = re.compile("|".join(re.escape(x) for x in BAND_POLICY_V104["national_body_words"]))
LOCAL_APPLY_R = re.compile(r"申报|入库|征集|指标|竞价|竞争性配置|遴选")
# 2026-09-20 测试轮（06-24 批次）M5 延伸：市级规划防护——地级市行政名＋(≤16字)＋十五五/十四五/
# 五年规划 = 市级规划本体，S-P02 国家重点规划高地板不触发（『电解海水制氢提镁纳入海口市
# “十五五”海洋经济发展规划』修复：海口不在省级名单，原走了国家地板）。
# 词形注意：市前字符排除 城/超（防『智慧城市/超市』把名词 市 吞进地名）；市后排除 市场/市民/
# 市值/市容/市区 等复合词。代价：盐城/宣城/聊城/运城/晋城 等以城结尾的地级市暂不识别（少数派，
# 留待域名表化）；落中地板 S-P03 仍保底不误伤。
CITY_PLAN_R = re.compile(r"[^\x00-\xff城超]{2,4}市(?![场民值化容区])[^，。！？、\n]{0,16}"
                         r"(?:十五五|十四五|五年规划)")
# M6：首座/首个/最大 × 商业化/示范（在建亦可，中地板）。
FIRST_PROJECT_R = re.compile(r"(?:首座|首个|首套|最大)[^，。！？\n]{0,14}(?:商业化|示范)|"
                             r"(?:商业化|示范)[^，。！？\n]{0,14}(?:首座|首个|首套|最大)", re.I)
# M7：题名工程里程碑事实（高地板）与百兆瓦级规模。
MILESTONE_TITLE_R = re.compile(r"倒送电|并网成功|并网一次性|投运成功|全流程贯通|全工艺流程贯通|"
                               r"一次性[^，。！？\n]{0,6}成功|调试成功|商业运营|商业化运营|正式运营", re.I)
SCALE_100MW_R = re.compile(r"\d{3,}\s*MW|\d+(?:\.\d+)?\s*GW|\d+(?:\.\d+)?\s*GWh", re.I)
# M8：科研转载载体证据 / 科研解读题名。
PAPER_REPOST_R = re.compile(r"论文|期刊|发表于|刊登|网络首发|学术速递|文献速递|文献|研究团队|研究发现|研究表明|"
                            r"DOI|arXiv|Nature|Science|Joule|Cell", re.I)
SCI_DIGEST_TITLE_R = re.compile(r"解密|难题|机理|解读|解析|进展|综述|学术速递|速递", re.I)
# M9：题名案例表达 / 技术风险词 / 量化证据。
CASE_TITLE_R = re.compile(r"如何|案例|实践|解密|解析", re.I)
RISK_TITLE_R = re.compile(r"硬伤|缺陷|致命|关闭|停产|事故|爆炸|火灾|污染|安全风险|风险", re.I)
RISK_TECH_R = re.compile(r"技术|工艺|热解|路线|材料|电池|储能|回收|碳|环保|节能", re.I)
QUANT_LEAD_R = re.compile(r"\d+(?:\.\d+)?\s*[%％]|万吨|\d+(?:\.\d+)?\s*万吨|\d{3,}\s*吨|\d+(?:\.\d+)?\s*亿|"
                          r"\d{2,}\s*MW|\d{2,}\s*GW|\d+(?:\.\d+)?\s*GWh", re.I)
# M10：标准首发/新制定题名。
STANDARD_FIRST_R = re.compile(r"首发|首次|首个|首部|新制定|最新实施|最新发布|最新版", re.I)
# M2：T18 技术参数判据（MW/GWh/MWh/kWh/% 等容量/效率参数——有则保留评分，无则按公告处理）。
T18_TECH_PARAM_R = re.compile(r"\d+(?:\.\d+)?\s*(?:MW|GWh|MWh|kWh|%|％)", re.I)

# ---- 2026-09-22 v1.06：第 5 轮反馈（3 条）S10 修订 ----
# #2：顶刊高地板收窄为 Nature/Science 正刊——子刊/姐妹刊（Nature Communications/Energy/Science Advances
# 等）不再触发，Joule/Cell/PNAS 同步退出高地板（『Nature Communications｜光伏电站的电表』这类
# 非瓶颈论文与中文转载统一中档；26.09.22 口径覆盖 26.09.19 #6 的『转载论文拉高』）。
TOP_JOURNAL_STRICT_R = re.compile(
    r"(?<![A-Za-z])(?:Nature|Science)(?![A-Za-z])(?!\s*(?:Communications|Energy|Materials|Sustainability|"
    r"Catalysis|Geoscience|Climate|Water|Food|Metabolism|Nanotechnology|Structural|Molecular|Biology|"
    r"Physics|Chemistry|Machine Intelligence|Plants|Astronomy|Microbiology|Biomedical|Immunology|"
    r"Neuroscience|Photonics|Electronics|Synapse|Aging|Ecology|Evolution|Genetics|Cities|Robotics|"
    r"Advances|Integration|大?子刊|旗下))", re.I)
# S-P01v2 载体语境守卫（v1.06b）：Nature/Science 命中点 ±16 字符内须有发表载体词，
# 排除普通名词用法（『Why science needs the humanities』的 science 是名词不是刊名）。
TOP_JOURNAL_CTX_R = re.compile(r"发|刊|论文|速递|published|journal|paper|magazine|正刊|子刊|《|》|：|:", re.I)


def _top_journal_strict_hit(title):
    for m in TOP_JOURNAL_STRICT_R.finditer(title or ""):
        if TOP_JOURNAL_CTX_R.search(title[max(0, m.start() - 16):m.end() + 16]):
            return True
    return False
# S-P09：论文关键瓶颈/突破锚定（26.09.18 #2 口径）——题名突破/纪录词 × 量化性能参数，缺一不可。
PAPER_BREAKTHROUGH_TITLE_R = re.compile(
    r"突破|纪录|新高|首次实现|首创|首个|刷新世界纪录|record|unprecedented|breakthrough|new record|"
    r"milestone|里程碑", re.I)

# ---- 2026-09-23 v1.08：第 7 轮裁决（W1/W2/W3/B1）S10 修订 ----
# W1/W2 未来态守卫：『预计10月转入商业运营』『下半年将在…部署』是将来时计划，事件未发生
# （将要建设≠建成，26.9.12 #4；本轮裁决：没投运/没部署 → 低，等做了再说）。
# 与在建态区分：开工/建设中/加快建设（FUTURE_PROJECT_R）仍可走 S-P05b 首座示范中地板。
FUTURE_LANDED_R = re.compile(
    r"(?:预计|拟|将|计划|有望|或将|将于|或于)[^，。；！？\n]{0,14}"
    r"(?:商业运营|商业化运营|正式运营|投入运营|投运|投产|并网|建成|交付|量产)", re.I)
FUTURE_DEPLOY_R = re.compile(
    r"将在|将部署|拟部署|计划部署|将建设|将建|将投运|将投产|将并网|将布局|将落地", re.I)
# W3 常规发电项目汇总稿：多个/一批×新能源项目×并网/投产 族——晶硅光伏/常规风电/水电等
# 成熟技术组合无创新性；题名点名低TRL新型发电技术除外（题名锚定，正文背景提及不豁免；
# 词表草案，可扩）。
BATCH_PROJECT_R = re.compile(r"多个|多项|一批|批量|陆续|汇总", re.I)
PROJECT_ACTION_R = re.compile(r"并网|投产|投运|开工|建设|发电|全容量|封顶", re.I)
GEN_TOPIC_R = re.compile(r"新能源|光伏|风电|水电|发电|电站", re.I)
NOVEL_GEN_R = re.compile(
    r"钙钛矿|量子点|有机光伏|有机太阳能|叠层|海上漂浮|漂浮式|波浪能|潮汐能|大容量风机|"
    r"单机[^，。！？\n]{0,10}(?:大容量|\d{2,}\s*MW)|(?:大容量|\d{2,}\s*MW)[^，。！？\n]{0,8}风机", re.I)
# B1 政策本体锚点与媒体解读框架：『出炉/定调投资方向/释放信号』是媒体主观理解 → 改判 T23
# 入参考区；《文件名》×发布/印发族或国家级主体词在题名 = 政策发布本体，仍走 T19（S-P02）。
POLICY_DOC_TITLE_R = re.compile(r"《[^》]{4,}》")
POLICY_RELEASE_ACT_R = re.compile(
    r"发布|印发|出台|公布|全文|获批|批复|征求意见|部署|发文|实施|召开", re.I)
POLICY_INTERPRET_R = re.compile(
    r"投资方向|投资机会|投资主线|投资布局|投资超|总投资|将超|超\d+(?:\.\d+)?万亿|赛道|风口|"
    r"释放[^，。！？\n]{0,8}信号|出炉|解读|梳理|前瞻|看点|哪些|定调|机会|探析", re.I)


def _policy_release_anchor(title):
    """B1 裁决（v1.08）：题名有政策本体锚点（《文件名》×发布/印发/出台族 或 国家级主体词）。"""
    return bool(POLICY_DOC_TITLE_R.search(title) and POLICY_RELEASE_ACT_R.search(title)) \
        or bool(NATIONAL_BODY_R.search(title))


def _is_focus_domain(dom):
    """聚焦领域（用户口径：电池、能源、零碳脱碳、AI、半导体、芯片）= P0 域族 ∪ E26 ∪ AI/零碳语义分支。"""
    p = dom.get("primary") or {}
    if not p:
        return False
    if str(p.get("no", "")) in P0_DOMAIN_NOS:
        return True
    hay = " ".join(str(p.get(k, "")) for k in ("path", "tree", "name", "branch"))
    if dom.get("llm"):
        # LLM 伪域按路径语义判断是否落入聚焦族（如“工程改进/陆路运输”不入）。
        return bool(FOCUS_EXTRA_R.search(hay))
    # 2026-09-19 v1.03b：E 域参数卡（能源侧/零碳产业树）已整体入 P0 域族；
    # 扩展域按路径分支判断（工业脱碳=GT125 石化脱碳、光电技术=GT128 光电器件属聚焦）。
    return bool(re.search(r"AI与智能科技|零碳产业|能量转化|能源侧|工业脱碳|光电技术", hay))


def _s10_policy(item, dom, typ, score):
    """v1.03 S10 档位政策：地板（瓶颈/首创/国家规划/顶刊/政策/一般技术）与
    上限（汽车白名单未中/生物医药无爆点/非聚焦/软信息/无技术细节/高TRL常规/宣传）。
    返回 (band, gateNotes, auditRows, tier_override)。不改写分数（S-V02 信源提示分除外）。"""
    tid = typ["tid"]
    title = item["title"]
    lead = item["body"][:1200]
    text = title + "\n" + lead
    band = score.get("band")
    notes, audit_rows, tier_override = [], [], None
    if band not in BAND_RANK:
        return band, notes, audit_rows, None
    p = dom.get("primary") or {}
    dom_hay = " ".join(str(p.get(k, "")) for k in ("path", "tree", "name", "branch"))
    focus = _is_focus_domain(dom)

    # —— 降级触发器 ——
    auto_hit = bool(AUTO_DOM_R.search(dom_hay) or AUTO_CONTENT_R.search(title)) and not AUTO_WHITELIST_R.search(text)
    bio_hit = bool(BIO_DOM_R.search(dom_hay)) and not BIO_HOTSPOT_R.search(text)
    llm_nonfocus = bool(dom.get("llm")) and not focus
    # 2026-09-20 v1.04（M5）：地方级项目申报/入库 = 硬上限——题名省级地名＋申报/入库/指标
    # 配置事件、且无国家级主体词（『湖南启动十五五风光项目入库申报』是地方程序性资源配置）。
    local_proc = bool(PROVINCE_R.search(title) and LOCAL_APPLY_R.search(title)
                      and not NATIONAL_BODY_R.search(title))

    # —— 升级触发器（v1.04 收紧/扩展）——
    # M1：瓶颈词必须题名锚定——正文导语的背景提及（『卷入出口管制风波』）与投标履约条款
    # （『交货期：合同签订后45天内交货』）不是瓶颈事件本体，不得抬档。
    bottleneck = focus and bool(BOTTLENECK_R.search(title)) and bool(BOTTLENECK_DEG_R.search(text))
    # M3：首创认证防护——(a)题名含基金/申报指南/大会/演讲等语境词时不触发（企业宣传
    # boilerplate 的『全球首创+cTÜVus认证』不是技术首证）；(b)在建/将建事件不触发
    # （建成>将建）；(c)落地族扩展 投运/商业运营/全流程贯通/倒送电/首座。
    pr_excluded = bool(FIRST_PR_EXCLUDE_R.search(title))
    future_project = bool(FUTURE_PROJECT_R.search(title) and not LANDED_IN_TITLE_R.search(title))
    # 2026-09-23 v1.08（W1/W2 裁决）：未来态计划——预计/将/拟×（时间）×投运·商业运营·并网，
    # 或 将在/将部署——将来时事件未发生，硬上限低（首座×示范在建仍走 S-P05b）。
    future_landed = bool(FUTURE_LANDED_R.search(title))
    future_deploy = bool(FUTURE_DEPLOY_R.search(title))
    first_verified = (not pr_excluded and not future_project and not future_landed and not future_deploy
                      and bool(FIRST_VERIFIED_R_V104.search(text)) and bool(FIRST_EVIDENCE_R_V104.search(text)))
    # M5：国家重点规划题名锚定须国家级——省级地名＋无国家级主体词 → 不触发；
    # 2026-09-20 测试轮补：市级规划（X市…十五五/十四五/五年规划）同样不触发，落 S-P03 中地板。
    # 2026-09-23 v1.08（B1 裁决）：题名还须有政策本体锚点——《文件名》×发布/印发/出台族或
    # 国家级主体词；媒体『出炉/定调/释放信号/投资方向』解读稿不再触发国家地板（改判 T23 入参考区）。
    national = bool(NATIONAL_POLICY_R.search(title)) and (
        not PROVINCE_R.search(title) or bool(NATIONAL_BODY_R.search(title))) and (
        not CITY_PLAN_R.search(title)) and _policy_release_anchor(title)
    top_journal = bool(TOP_JOURNAL_R.search(title))
    # M7：题名工程里程碑；M6：首座/首个/最大×商业化/示范工程（在建亦可）。
    title_milestone = bool(MILESTONE_TITLE_R.search(title))
    first_project = bool(FIRST_PROJECT_R.search(title))
    # 2026-09-23 v1.08（W1/W2/W3 裁决）：未来态计划硬上限（首座×示范在建 first_project 豁免，
    # 保 S-P05b 中地板）与常规发电项目汇总稿硬上限（晶硅/常规风电/水电组合无创新性；
    # 题名点名低TRL新型发电技术除外——词表 NOVEL_GEN_R 草案）。
    future_plan = (future_landed or future_deploy) and not first_project
    batch_gen_roundup = (tid in {"T08", "T10"} and bool(BATCH_PROJECT_R.search(title))
                         and bool(PROJECT_ACTION_R.search(title)) and bool(GEN_TOPIC_R.search(title))
                         and not NOVEL_GEN_R.search(title))
    # M2：招投标公告（题名锚定）且无技术参数 → 无条件低档。
    bid_announce = tid == "T18" and bool(BID_ANNOUNCE_R.search(title)) and not T18_TECH_PARAM_R.search(text)
    # M8：科研转载载体；M9：实质技术案例/风险报道。
    source_hint_hit = any(a in str(item.get("meta") or "") for a in BAND_POLICY_V103["source_hint_accounts"])
    paper_repost = bool(PAPER_REPOST_R.search(title + "\n" + lead)) or (
        source_hint_hit and bool(SCI_DIGEST_TITLE_R.search(title)))
    substantive_case = (bool(CASE_TITLE_R.search(title))
                        or bool(RISK_TITLE_R.search(title) and RISK_TECH_R.search(title))
                        ) and bool(QUANT_LEAD_R.search(title + "\n" + lead))

    floor, floor_reason, floor_tier = None, "", None
    # 2026-09-19 v1.03b：硬上限（S-A01 汽车白名单未中/S-A02 生物无爆点/S-A03 非聚焦）
    # 优先于一切地板——用户口径“整车宣传/无关领域内容没啥用”不受技术类地板豁免
    # （修复：华为乾崑量产 T08 的 S-P05 中地板曾挡住 S-A01 低上限）。
    # 2026-09-20 v1.04：S10-D 地方级项目申报/入库并入硬上限。
    # 2026-09-23 v1.08：S-A05 未来态计划 / S-A04 常规发电项目汇总稿 并入硬上限（W1/W2/W3 裁决）。
    hard_cap = auto_hit or bio_hit or llm_nonfocus or local_proc or future_plan or batch_gen_roundup
    # 2026-09-19 v1.03c：投融资/并购/企业经营/会议活动（T11/T13/T14/T24）无条件低档，
    # 内容地板不得豁免（用户口径：投融资、会议、宣传文案→低）——修复：天合融资、
    # 太空光伏论坛宣传（早鸟倒计时/报告征集）因正文含『首创+认证』曾被 S-F01 抬成高。
    # 2026-09-20 v1.04（M2）：T18 招投标公告（中标/预中标/候选人公示/招标）无技术参数同列
    # （用户 09-12/09-17/09-20 三轮口径：预中标/中标/招标无技术细节没啥用）。
    # T12 合作/T16 市场/T21 人才/T22 观点/T23 分析仍可经地板升档（政策评论/顶刊转载/科研转载）。
    no_floor_soft = tid in {"T11", "T13", "T14", "T24"} or bid_announce
    if not hard_cap and not no_floor_soft:
        if bottleneck:
            floor, floor_tier = "高", "P0"
            floor_reason = "S-B01 瓶颈事实：题名锚定供应瓶颈＋程度/量化证据（重点瓶颈=高档本体载荷）→ 档位地板=高"
        elif first_verified and focus and tid in {"T06", "T07", "T08", "T09", "T10"}:
            floor, floor_tier = "高", "P0"
            # 2026-09-24 v1.09（v101 复核）：S-F01 限技术事件类 T06–T10——首证事实以载体为本位
            # （认证/工程验证/项目/产品/运行）；T12 合作·T16 市场·T17 供应链等软类型不再经正文
            # boilerplate『首个+认证』背景句抬档（v1.01 口径：战略合作/招聘题名不得高档；
            # v1.03c 意图：软类型可用的地板是政策评论/顶刊/科研转载，不含首证通道）。
            floor_reason = ("S-F01 首创认证：『首个/首创＋认证/标准/投产/投运/商业运营』首证事实"
                            "（技术事件类 T06–T10；已排除基金·会议语境与在建态） → 档位地板=高")
        elif (focus and tid in {"T08", "T10"} and title_milestone and not future_landed
              and SCALE_100MW_R.search(title)):
            floor, floor_tier = "高", "P0"
            floor_reason = ("S-F02 题名工程里程碑：百兆瓦级以上规模＋倒送电/并网成功/全流程贯通/商业运营里程碑"
                            "（里程碑是事件本体，非宣传数字）→ 档位地板=高")
        elif national and focus:
            floor, floor_tier = "高", "P0"
            floor_reason = ("S-P02 国家重点规划：题名锚定十五五/部委部署/国家重点研发＋政策本体锚点"
                            "（《》文件名×发布/印发族或国家级主体；v1.08 B1——媒体出炉/定调/信号解读稿"
                            "不触发；省级地方申报不触发） → 档位地板=高（政策优先级拉高）")
        elif focus and tid in {"T01", "T05"} and top_journal:
            floor, floor_tier = "高", "P0"
            floor_reason = "S-P01 顶刊论文：聚焦域 Nature/Science/Joule/Cell/PNAS 转载 → 档位地板=高（转载论文优先）"
        elif tid == "T19" and focus:
            floor, floor_tier = "中", "P1"
            floor_reason = "S-P03 聚焦域政策与战略事件 → 档位地板=中"
        elif focus and tid in {"T22", "T23"} and paper_repost:
            floor, floor_tier = "中", "P1"
            floor_reason = ("S-P06 科研转载/解读：聚焦域×科研载体证据（论文/期刊/研究团队，或专业编辑信源×"
                            "科研解读题名）→ 档位地板=中（科研文献转载都是中，不放低）")
        elif focus and tid in {"T22", "T23"} and substantive_case:
            floor, floor_tier = "中", "P1"
            floor_reason = ("S-P07 实质技术案例/风险报道：题名案例表达或技术风险词＋量化证据"
                            "（区别于无实质观点的嘴炮）→ 档位地板=中")
        elif focus and tid == "T20" and STANDARD_FIRST_R.search(title):
            floor, floor_tier = "中", "P1"
            floor_reason = "S-P08 首部/首发技术标准：聚焦域×中低TRL领域标准发布（制度性卡点）→ 档位地板=中"
        elif (focus and tid in {"T01", "T03", "T04", "T05", "T06", "T07", "T09"}
              and score.get("scoreStatus") == "已评分" and str(score.get("evidenceLevel")) != "E4"):
            floor, floor_tier = "中", None
            floor_reason = "S-P04 一般技术类：聚焦域×技术事件型（非计划态）→ 档位地板=中"
        elif (focus and tid in {"T08", "T10"} and score.get("scoreStatus") == "已评分"
              and str(score.get("evidenceLevel")) != "E4"
              and (LANDED_FACT_R.search(title) or first_project)):
            floor, floor_tier = "中", None
            floor_reason = ("S-P05 产业化落地：聚焦域设施/装备落地事实（含首座/首个/最大×商业化/示范工程在建，"
                            "S-P05b）→ 档位地板=中")

    cap, cap_reason = None, ""
    if auto_hit:
        cap = "低"
        cap_reason = ("S-A01 汽车白名单未中：仅固态/钠电/新型电池/光伏器件装车/直接CCUS降碳/电网车网结合/"
                      "智能驾驶升阶计入技术事件，其余整车动态按宣传文案后置 → 档位上限=低（硬上限，优先于地板）")
    elif bio_hit:
        cap = "低"
        cap_reason = "S-A02 生物医药无爆点（克隆/脑机接口/复活等）→ 档位上限=低并后置（硬上限，优先于地板）"
    elif llm_nonfocus:
        cap = "低"
        cap_reason = "S-A03 非聚焦领域（电池/能源/零碳脱碳/AI/半导体/芯片外）→ 档位上限=低并后置（硬上限，优先于地板）"
    elif local_proc:
        cap = "低"
        cap_reason = ("S10-D 地方级项目申报/入库：省级地名＋申报/入库/指标配置且非国家级主体，"
                      "地方程序性资源配置不是国家规划本体 → 档位上限=低（硬上限，优先于地板）")
    elif future_plan:
        cap = "低"
        cap_reason = ("S-A05 未来态计划（v1.08 W1/W2 裁决）：预计/将/拟×（时间）×投运·商业运营·并网 或 "
                      "将在/将部署——将来时计划事件未发生（将要建设≠建成；没投运/没部署 → 低，"
                      "等做了再说；首座×示范在建仍走 S-P05b 中地板）→ 档位上限=低（硬上限，优先于地板）")
    elif batch_gen_roundup:
        cap = "低"
        cap_reason = ("S-A04 常规发电项目汇总稿（v1.08 W3 裁决）：多个/一批×新能源项目×并网/投产 族——"
                      "晶硅光伏/常规风电/水电等成熟技术组合无创新性，一律低；题名点名钙钛矿/量子点/有机/"
                      "海上漂浮式/单机大容量风机等低TRL新型发电技术除外（题名锚定，正文背景提及不豁免）"
                      " → 档位上限=低（硬上限，优先于地板）")
    elif floor is None:
        if tid in SOFT_LOW_TYPES:
            cap = "低"
            cap_reason = "S10-B 软信息类型（投融资/并购/市场/会议/宣传/观点/招聘）无技术瓶颈载荷 → 档位上限=低"
        elif tid in PROC_LOW_TYPES:
            t18_tech = tid == "T18" and bool(T18_TECH_PARAM_R.search(text))
            t20_high = tid == "T20" and (national or bool(re.search(r"全球|国际", title, re.I) and re.search(r"首个|首次", title, re.I)))
            if not (t18_tech or t20_high):
                cap = "低"
                cap_reason = ("S10-C 无技术细节的建厂/招标/立项/资源与法规常规动态（T18 无技术参数——"
                              "v1.04 起招投标公告无条件低档、地板不豁免；T20 非国家规划/全球首个标准豁免）→ 档位上限=低")
        elif _high_trl_routine(item, typ, score):
            cap = "低"
            cap_reason = "S10-C 高TRL常规产业动态（无阶段跃迁/纪录/机制变化）→ 档位上限=低"

    if floor:
        if BAND_RANK[band] < BAND_RANK[floor]:
            notes.append(f"S10 地板：{floor_reason}（{band}→{floor}）")
            audit_rows.append(["S10", "档位政策·地板", floor_reason + f"；最终档位=max({band}, {floor})={floor}"])
            band = floor
        else:
            audit_rows.append(["S10", "档位政策·地板确认", floor_reason + f"；当前档位 {band}≥{floor}，维持"])
        tier_override = floor_tier or tier_override
    elif cap and BAND_RANK[band] > BAND_RANK[cap]:
        notes.append(f"S10 上限：{cap_reason}（{band}→{cap}）")
        audit_rows.append(["S10", "档位政策·上限", cap_reason + f"；最终档位=min({band}, {cap})={cap}"])
        band = cap
        tier_override = "P2"
    # 2026-09-20 v1.04：硬上限命中但档位已为低时也要留审计痕迹并后置 P2（湖南入库申报）。
    if local_proc and tier_override is None:
        tier_override = "P2"
        if not any(str(r[1]).startswith("档位政策·上限") for r in audit_rows):
            audit_rows.append(["S10", "档位政策·上限确认",
                               "S10-D 地方级项目申报/入库（省级地名＋申报/入库，非国家级主体）→ 档位已为低，维持并后置 P2"])
    # 2026-09-23 v1.08：S-A04 常规发电项目汇总稿 / S-A05 未来态计划 同样处理——档位已为低
    # 时不留空审（S8 直接低分的短稿也要可追溯为何后置 P2）。
    if (future_plan or batch_gen_roundup) and tier_override is None:
        tier_override = "P2"
        if not any(str(r[1]).startswith("档位政策·上限") for r in audit_rows):
            audit_rows.append(["S10", "档位政策·上限确认",
                               "S-A04 常规发电项目汇总稿 / S-A05 未来态计划（v1.08 硬上限）→ 档位已为低，维持并后置 P2"])

    # —— 2026-09-22 v1.06：论文及中文科研转载统一档位政策（用户 26.09.22 #1/#2）——
    # 论文类（T01 与 T22/T23×科研转载载体）默认中档；高档仅两条通路：
    #   (a) S-P01v2 Nature/Science 正刊（收窄：子刊/姐妹刊不再触发，Joule/Cell/PNAS 退出）；
    #   (b) S-P09 题名突破/纪录锚定 × 量化性能参数（26.09.18 #2 瓶颈参数突破口径）。
    # S-A03 非聚焦与 S10-C 常规动态不再把论文压到低（『蓝碳红树林』『TacForeSight』修复）；
    # S-V02 专业编辑信源只加分，不联动档位。
    paper_class = tid == "T01" or (tid in {"T22", "T23"} and paper_repost)
    if paper_class and band in BAND_RANK:
        top_strict = focus and tid in {"T01", "T05"} and _top_journal_strict_hit(title)
        paper_breakthrough = bool(PAPER_BREAKTHROUGH_TITLE_R.search(title)) and bool(QUANT_LEAD_R.search(text))
        if top_strict:
            if BAND_RANK[band] < BAND_RANK["高"]:
                notes.append(f"S10 地板：S-P01v2 顶刊正刊：聚焦域 Nature/Science 正刊（子刊不算）→ 档位地板=高（{band}→高）")
                audit_rows.append(["S10", "档位政策·地板",
                                   "S-P01v2 顶刊正刊（v1.06 收窄）：Nature/Science 正刊转载 → 档位地板=高"])
                band = "高"
                tier_override = "P0"
            else:
                audit_rows.append(["S10", "档位政策·地板确认",
                                   f"S-P01v2 顶刊正刊（v1.06 收窄）：当前档位 {band}≥高，维持"])
        elif paper_breakthrough:
            if BAND_RANK[band] < BAND_RANK["中"]:
                notes.append(f"S10 地板：S-P09 论文突破锚定：题名突破/纪录词×量化参数 → 档位地板=中（{band}→中）")
                audit_rows.append(["S10", "档位政策·地板",
                                   "S-P09 论文突破锚定（v1.06）：保持原档位，最低中"])
                band = "中"
            else:
                audit_rows.append(["S10", "档位政策·确认",
                                   f"S-P09 论文突破锚定（v1.06）：题名突破词×量化参数 → 维持原档位 {band}"])
        elif band != "中":
            notes.append(f"S10 论文统一档位：S-P10 非瓶颈非正刊论文/中文转载 → 统一中档（{band}→中）")
            audit_rows.append(["S10", "档位政策·论文统一中档",
                               "S-P10（v1.06）：论文及中文科研转载非关键瓶颈、非 Nature/Science 正刊 → "
                               "统一中档；S-V02 信源提示只加分不联动档位"])
            band = "中"
            tier_override = None
    return band, notes, audit_rows, tier_override
# 高TRL常规动态后置只作用于运行/市场/经营/分析类事件，论文与验证类不受此规则影响。
_DEMOTE_TYPES = {"T08", "T10", "T11", "T12", "T16", "T17", "T23"}
_STAGE_JUMP_R = re.compile(
    r"纪录|首次|首创|首个|突破|开工|奠基|建成|投产|投运|并网|封顶|交付|量产|扩容|扩建|发布|推出|上线|"
    r"机制|新规|规则|办法|方案|record|first|breakthrough|launch|commissioned|online|expansion|unveil", re.I)


def _is_p0_domain(dom):
    p = dom.get("primary") or {}
    if str(p.get("no", "")) in P0_DOMAIN_NOS:
        return True
    # AI与半导体芯片族：语义叶路径或扩展域名含 AI 分支/半导体/芯片/集成电路/光电关键词。
    hay = " ".join(str(p.get(k, "")) for k in ("path", "tree", "name"))
    return bool(re.search(r"AI与智能科技|人工智能|大模型|语言模型|半导体|芯片|集成电路|光电", hay))


def _high_trl_routine(item, typ, score):
    """P0 域内 TRL≥9 且事件为常规运行/市场波动（无阶段跃迁、无纪录、无机制变化）→ True。"""
    if typ["tid"] not in _DEMOTE_TYPES:
        return False
    band = str((score.get("trlInfo") or {}).get("band") or "")
    m = re.match(r"(\d+)", band)
    if not m or int(m.group(1)) < 9:
        return False
    return not _STAGE_JUMP_R.search(item["title"])


def _priority_tier(item, dom, typ, score, tier_override=None):
    """排序键第一维：P0 技术优先 / P1 产业与制度 / P2 软信息与高TRL常规动态后置。
    v1.03：S10 地板/上限政策可直接指定层（瓶颈/首创/国家规划/顶刊→P0；降级→P2）。"""
    if tier_override:
        return tier_override
    if _high_trl_routine(item, typ, score) or typ["tid"] in TYPES_P2_NOS:
        return "P2"
    if _is_p0_domain(dom) and typ["tid"] in TYPES_P0_NOS:
        return "P0"
    return "P1"


# ---- v1.05（2026-09-22）C-R01/C-R03 事件级去重（管线末端模块）----
# 读取层只有完全同题去重；本模块在分类评分完成后按事件簇合并：
#   C-R01 论文：标准化 DOI 精确匹配（跨源）；
#   C-R03 新闻：题名《》文号/文件名匹配 + 题名 bigram 相似度（同域、日期窗内）。
# 常数为草案值（null 待回测校准，同 S-V02 惯例）。
EVENT_DEDUP_PARAMS = {
    "title_jaccard_min": 0.75,   # 新闻题名 bigram Jaccard 阈值
    "date_window_days": 2,       # 同事件日期窗（news RSS 滞后容差）
    "doc_name_min_chars": 8,     # 《》文号名参与聚类的最短规范长度（排除刊名）
}

_DOI_PREFIX_R = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
_EVT_STRIP_R = re.compile(r"[^0-9A-Za-z一-鿿]+")
_QUALITY_RANK = {"full": 3, "abstract": 2, "preview": 2, "digest": 1, "empty": 0}
_EVID_RANK = {"E1": 3, "E2": 2, "E3": 1}


def _norm_doi(d):
    return _DOI_PREFIX_R.sub("", (d or "").strip()).replace(" ", "").lower()


def _doc_key_names(title):
    """题名中的《》文号/文件名（规范后 ≥8 字符）；《刊名》+栏目词的期刊载体模式不参与。"""
    names = []
    for seg in re.findall(r"《([^《》]{4,40})》", title or ""):
        norm = _EVT_STRIP_R.sub("", seg)
        if len(norm) < EVENT_DEDUP_PARAMS["doc_name_min_chars"]:
            continue
        tail = (title.split(f"《{seg}》", 1)[1] if f"《{seg}》" in title else "")[:4]
        if re.match(r"^\s*(文章|独家|目录|期刊|杂志|报道)", tail):
            continue
        names.append(norm)
    return names


def _bigrams(s):
    s = _EVT_STRIP_R.sub("", (s or "").lower())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else ({s} if s else set())


def _title_jaccard(a, b):
    A, B = _bigrams(a), _bigrams(b)
    return len(A & B) / len(A | B) if A and B else 0.0


# v1.06b：系列文防误并——题名尾部（上）/（下）/（一）/（二）/（1）等分节标记是不同文章，
# 双方都有分节标记且标记不同时不并簇（『2025年储能技术研究进展（上）（下）』是两篇）。
_SERIAL_TAG_R = re.compile(r"[（(]\s*(上|下|中|终|完|[一二三四五六七八九十]|\d{1,2})\s*[)）]\s*$")


def _serial_tag(title):
    m = _SERIAL_TAG_R.search(title or "")
    return m.group(1) if m else ""


def _merge_rank(x):
    """主记录优先级（C-R03：原发/权威/正文最完整者为主记录；更早发布优先）。"""
    try:
        d = date.fromisoformat(x["date"]).toordinal()
    except (ValueError, TypeError):
        d = 99999999
    return (_QUALITY_RANK.get(x.get("contentQuality"), 0),
            _EVID_RANK.get(x.get("evidenceLevel"), 0),
            len(x.get("bodyPrep") or ""),
            -d)


def _dedup_events(items):
    """事件级去重（分类评分完成后、写盘前）：返回 (去重后列表, 并入条数)。

    候选排除：域外 / T25（信息不足型不参与合并，也不被并入）；
    v1.11 起范围忽略记录正常参与合并（ignored 仅审计，不拦截任何输出）。
    并入记录保留 provenance 到主记录 mergedRefs，评分只保留主记录一次。
    """
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    def days_apart(x, y):
        try:
            return abs(date.fromisoformat(x["date"]).toordinal() - date.fromisoformat(y["date"]).toordinal())
        except (ValueError, TypeError):
            return 99

    window = EVENT_DEDUP_PARAMS["date_window_days"]
    # C-R01 论文：标准化 DOI 精确匹配（跨源；读取层完全同题去重已先行）
    by_doi = {}
    for i, x in enumerate(items):
        if x["typeId"] != "T01" or x["domainDisp"] == "域外":
            continue
        nd = _norm_doi(x.get("doi"))
        if not nd:
            continue
        if nd in by_doi:
            union(i, by_doi[nd])
        else:
            by_doi[nd] = i
    # C-R03 新闻：《》文号/文件名匹配（日期窗内；不要求同域——文号即事件身份，
    # 同文号异域属分类不一致，合并后保留主记录判定）
    news_idx = [i for i, x in enumerate(items)
                if x["src"] in ("news-spider", "wechat")
                and x["domainDisp"] != "域外" and x["typeId"] != "T25"]
    doc_map = {}
    for i in news_idx:
        for name in _doc_key_names(items[i]["title"]):
            j = doc_map.get(name)
            if j is not None:
                if days_apart(items[i], items[j]) <= window:
                    union(i, j)
            else:
                doc_map[name] = i
    # C-R03 新闻：题名 bigram 相似度（同域、日期窗内）
    thr = EVENT_DEDUP_PARAMS["title_jaccard_min"]
    for a in range(len(news_idx)):
        for b in range(a + 1, len(news_idx)):
            i, j = news_idx[a], news_idx[b]
            if find(i) == find(j) or items[i]["domainId"] != items[j]["domainId"]:
                continue
            if days_apart(items[i], items[j]) > window:
                continue
            ta, tb = _serial_tag(items[i]["title"]), _serial_tag(items[j]["title"])
            if ta and tb and ta != tb:
                continue  # v1.06b：系列文分节（上/下）是不同文章，不并簇
            if _title_jaccard(items[i]["title"], items[j]["title"]) >= thr:
                union(i, j)
    # 簇合并：主记录 = 正文最完整 · 证据层级最高 · 最早发布
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    keep = [True] * n
    merged_ct = 0
    for members in groups.values():
        if len(members) < 2:
            continue
        main = max(members, key=lambda i: (_merge_rank(items[i]), -i))
        refs = []
        for i in members:
            if i == main:
                continue
            keep[i] = False
            refs.append({"title": items[i]["title"], "src": items[i]["src"], "meta": items[i]["meta"],
                         "url": items[i]["url"] or items[i]["doi"], "date": items[i]["date"],
                         "band": items[i]["scoreBand"], "value": items[i]["valueDisplay"]})
            merged_ct += 1
        m = items[main]
        m["duplicates"] = (m.get("duplicates") or 0) + len(refs)
        m["mergedRefs"] = refs
        m["gateActions"] = list(m.get("gateActions") or []) + [
            f"C-R03 同事件合并：{len(refs)} 条同事件记录并入（DOI/文号/题名匹配；主记录=正文最完整·证据最高·最早发布）"]
        m["scoreAudit"] = list(m.get("scoreAudit") or []) + [
            ["C-R03", "同事件合并", "并入：" + "；".join(r["title"][:40] for r in refs)]]
    out = [x for i, x in enumerate(items) if keep[i]]
    if merged_ct:
        print(f"[event-dedup] C-R01/C-R03 事件级合并 {merged_ct} 条（记录 {n}→{len(out)}）")
    return out, merged_ct


def build():
    rows = base.read_rows()
    raw_n = len(rows)
    seen, dedup = {}, []
    for item in rows:
        key = _norm_title(item["title"]) or item.get("url", "")
        if key in seen:
            seen[key]["duplicates"] += 1
            continue
        item["duplicates"] = 0
        seen[key] = item
        dedup.append(item)

    out = []
    llm_decisions = _load_llm_decisions()
    for item in dedup:
        dom = classify_domain_semantic(item)
        typ = classify_type_semantic(item)
        # v1.02：大模型语义判定（两份基准 docx）覆盖规则层结果；规则层留作参考痕迹。
        llm_dec = llm_decisions.get(item.get("url") or "")
        if llm_dec:
            _nd = _llm_override_dom(llm_dec, dom)
            _nt = _llm_override_typ(llm_dec, typ)
            if _nd:
                dom = _nd
            if _nt:
                typ = _nt
        # 2026-09-23 v1.08（B1 裁决）：十五五/规划类媒体投资解读稿改判 T23——题名无政策本体
        # 锚点（无《文件名》×发布/印发族、无国家级主体词）且带 出炉/定调/释放信号/投资方向/
        # 总投资将超 等媒体主观理解框架 → 媒体分析入深度分析（参考区，评分仅参考）；国家政策
        # 明确发布《规划》或部委发文的仍走 T19 主榜（S-P02 高）。
        _interp_retyped = False
        if (typ["tid"] == "T19" and dom.get("primary") and dom["disp"] != "域外"
                and NATIONAL_POLICY_R.search(item["title"])
                and POLICY_INTERPRET_R.search(item["title"])
                and not _policy_release_anchor(item["title"])):
            _interp_retyped = True
            typ = type_result(
                "T23", "C-T08/T19-媒体解读改判（B1）",
                "题名是规划话题×媒体解读框架（出炉/定调/释放信号/投资方向/总投资将超），无政策发布本体锚定；"
                "媒体主观理解入深度分析（参考区），国家政策明确说了的仍走 T19 主榜",
                "题名: " + item["title"][:60], ["T19"], "规则裁决")
        outside_reason, outside_detail, outside_topic = ("", "", "")
        if dom["disp"] == "域外":
            outside_reason, outside_detail, outside_topic = _outside_analysis(item, typ)
        # 2026-09-25 v1.11（用户口径修订）：不设 参考/待定/忽略 类目——
        # 入域记录一律直接按机制给出 高/中/低（T25 经通用技术卡兜底）；域外不评分。
        # 范围忽略（ignored）降为纯审计字段，不再拦截评分，也不构成 attention 状态。
        ignored = base.catl_scope_ignore_reason(item)
        eligible = bool(dom["primary"]) and dom["disp"] != "域外"
        generic_domain = dom["disp"] in ("主域(语义域)", "主域(扩展)") or bool(dom.get("llm"))
        score = {"value": None, "valueDisplay": "—", "raw": None, "gated": None, "band": "未评分",
                 "dimensions": [], "trlInfo": None, "weight": None, "cap": None,
                 "evidenceLevel": "未判", "gateActions": [], "missingEvidence": [],
                 "scoreStatus": "未进入评分", "audit": []}
        card, card_name = None, None
        if eligible and generic_domain:
            card = typ["card"]
            card_name = base.CARDS[card].get("name", card) if card else "通用类型机制"
            score = _unregistered_domain_score(item, typ, dom["primary"], dom)
        elif eligible and typ["card"] and dom["primary"]:
            support = _score_support(item, dom)
            card = typ["card"]
            card_name = base.CARDS[card].get("name", card)
            score = _score_by_mechanism(item, typ, dom["primary"], support)
        elif eligible and dom["primary"]:
            support = _score_support(item, dom)
            score = _score_by_mechanism(item, typ, dom["primary"], support)
        if _interp_retyped:
            score["gateActions"] = list(score.get("gateActions") or []) + [
                "B1 媒体投资解读改判：T19→T23（题名无政策发布锚点×出炉/定调/信号/投资方向框架）→ 深度分析参考区（26.09.23 裁决）"]
            score["audit"] = list(score.get("audit") or []) + [
                ["S2", "类型改判·B1（v1.08）",
                 "T19→T23 深度分析：规划话题×媒体解读框架且无《》/发布·印发/国家级主体锚点——"
                 "媒体主观理解入参考区；国家政策明确说了的（政策发布本体）仍走 T19 主榜高"]]
        # v1.11：attention 只剩 高/中/低/域外——入域直接取机制档位（含 T02 S-R01 粗分档、
        # T25 通用卡兜底）；域外＝没进域，不评分。
        if dom["disp"] == "域外":
            attention = "域外"
        else:
            attention = score["band"]
        # ---- v1.02 优先级分层（U_type 档位上限）+ v1.03 S10 档位政策（地板/上限）+ P0/P1/P2 排序层 ----
        priority_tier = ""
        if attention in BAND_RANK:
            cap = TYPE_BAND_CAP.get(typ["tid"])
            if cap and BAND_RANK.get(score.get("band"), -1) > BAND_RANK[cap]:
                old_band = score["band"]
                score["band"] = cap
                score["gateActions"] = list(score.get("gateActions") or []) + [
                    f"U_type({typ['tid']}) 档位上限：{old_band}→{cap}（v1.02 优先级分层；分数不变）"]
                score["audit"] = list(score.get("audit") or []) + [
                    ["S9", "类型档位上限 U_type", f"最终档位=min({old_band}, {cap})={cap}；软信息类型不占用高关注位"]]
                if attention == old_band:
                    attention = cap
            # v1.03 S10 档位政策层：地板（瓶颈/首创/国家规划/顶刊/政策/一般技术）与
            # 上限（汽车白名单未中/生物医药无爆点/非聚焦/软信息/无技术细节/高TRL常规）。
            s10_band, s10_notes, s10_audit, s10_tier = _s10_policy(item, dom, typ, score)
            if s10_notes or s10_audit or s10_tier:
                score["band"] = s10_band
                score["gateActions"] = list(score.get("gateActions") or []) + s10_notes
                score["audit"] = list(score.get("audit") or []) + s10_audit
                attention = s10_band
            if eligible:
                priority_tier = _priority_tier(item, dom, typ, score, tier_override=s10_tier)
        # 2026-09-25 v1.11（用户口径修订）：v1.07 参考区分区停用——不设"参考"类目，
        # T02 研究报告/T23 深度分析入域后直接输出机制真实档位（S-R01 粗分档/S10 政策照常）。
        # section/bandUnderlying 字段保留（恒 主榜/同档位），S1–S10 评分与审计链不变。
        section, band_underlying = "主榜", score.get("band")
        trl_info = score.get("trlInfo") or {}
        # v1.09 展示链路：纯展示标注（域外记录标“域外”），在评分/档位/分区全部落定后追加，不影响任何判定。
        # 论文（T01）四分型逐条判定（用户 2026-09-24 口径：综述/研究型/分析类/新闻·评论·观点）。
        _dc = (("—", "域外", "—") if dom["disp"] == "域外"
               else DISPLAY_CHAIN_MAP.get(typ["tid"], ("待定", "信息不足", "—")))
        if dom["disp"] != "域外" and typ["tid"] == "T01":
            _dc = ("论文", _paper_display_subtype(item["src"], item["title"], item.get("body", "")), "A")
        out.append({
            "date": item["date"], "src": item["src"], "meta": item["meta"], "title": item["title"],
            "url": item["url"], "doi": item.get("doi", ""), "duplicates": item["duplicates"],
            "domain": dom["label"], "domainId": dom["primary"]["id"] if dom["primary"] else "",
            "domainDisp": dom["disp"], "domainConfidence": dom["confidence"], "domainRule": dom["rule"],
            "domainReason": dom["reason"], "domainTerms": dom["terms"], "domainSnippet": dom["snippet"],
            "secondaryDomains": [f"{d['no']} {d['name']}" for d in dom["secondary"]],
            "type": typ["label"], "typeId": typ["tid"], "typeRule": typ["rule"],
            "typeReason": typ["reason"], "typeEvidence": typ["evidence"],
            "typeAlternatives": typ["alternatives"], "typeConfidence": typ["confidence"],
            "family": typ["family"], "card": card, "cardName": card_name,
            "priorityTier": priority_tier, "section": section, "bandUnderlying": band_underlying,
            "displayCategory": _dc[0], "displaySubcategory": _dc[1], "displayClass": _dc[2],
            "llmJudged": bool(llm_dec),
            "value": score["value"], "valueDisplay": score["valueDisplay"], "attention": attention,
            "scoreBand": score["band"], "scoreStatus": score["scoreStatus"],
            "scoreRaw": score["raw"], "scoreAfterGate": score["gated"], "dimensions": score["dimensions"],
            "route": trl_info.get("route", ""), "routeTrlBand": trl_info.get("band", ""),
            "routeTrlBasis": trl_info.get("basis", ""), "trl": trl_info.get("trl"),
            "weight": score["weight"], "cap": score["cap"], "evidenceLevel": score["evidenceLevel"],
            "gateActions": score["gateActions"], "missingEvidence": score["missingEvidence"],
            "scoreAudit": score["audit"],
            "ignored": bool(ignored), "ignoredReason": ignored,
            "bodyPrep": item.get("body_prep", ""), "contentQuality": item.get("content_quality", ""),
            "outsideReason": outside_reason, "outsideReasonDetail": outside_detail, "outsideTopic": outside_topic,
        })

    # v1.02 排序键 = (分区, 日期, 优先级层 P0<P1<P2, -S8 分值, 关注, 标题)；分层不改写分数本身。
    # v1.07：参考区（T02/T23）整体排主榜之后，看板分表展示。
    out.sort(key=lambda x: (0 if x["section"] != "参考区" else 1, x["date"],
                            TIER_RANK.get(x["priorityTier"], 9), -(x["value"] or 0),
                            x["attention"], x["title"]))
    # v1.05 事件级去重（C-R01/C-R03 末端模块）：论文 DOI、新闻文号名/题名相似
    out, event_merged = _dedup_events(out)
    # 2026-09-25 v1.11（用户口径修订）：不设 参考/待定/忽略 类目——
    # 入域记录直接按机制输出 高/中/低（T02 走 S-R01 报告粗分档、T25 经通用技术卡兜底、
    # 范围忽略不再拦截评分）；域外不评分。主输出即全集，无过滤、无第五件套存档。
    # typePending/refZone/manual 保留为审计计数（后两者恒 0，供历史契约核对）。
    stats = {
        "raw": raw_n, "records": len(out),
        "duplicates": sum(x["duplicates"] for x in out),
        "eventMerged": event_merged,
        "mainDomain": sum(x["domainDisp"] in ("主域", "主域(草案)", "主域(语义域)", "主域(扩展)") for x in out),
        "semanticOnly": sum(x["domainDisp"] in ("主域(语义域)", "主域(扩展)") for x in out),
        "domainReview": 0,
        "outOfScope": sum(x["domainDisp"] == "域外" for x in out),
        "typePending": sum(x["typeId"] == "T25" for x in out),
        "semanticBoundary": sum(x["typeConfidence"] == "规则裁决" for x in out),
        "high": sum(x["scoreBand"] == "高" for x in out),
        "medium": sum(x["attention"] == "中" for x in out),
        "low": sum(x["attention"] == "低" for x in out),
        "unscored": sum(x["scoreBand"] == "未评分" for x in out),
        "refZone": sum(x["section"] == "参考区" for x in out),
        "manual": sum(x["attention"] == "待定" for x in out),
        "p0": sum(x["priorityTier"] == "P0" for x in out),
        "p1": sum(x["priorityTier"] == "P1" for x in out),
        "p2": sum(x["priorityTier"] == "P2" for x in out),
        "bandCapped": sum(any("U_type" in str(g) or "S10" in str(g) for g in x["gateActions"]) for x in out),
        "s10Floored": sum(any("S10 地板" in str(g) for g in x["gateActions"]) for x in out),
        "s10Capped": sum(any("S10 上限" in str(g) for g in x["gateActions"]) for x in out),
        "sourceHinted": sum(any("S-V02" in str(g) for g in x["gateActions"]) for x in out),
        "llmJudged": sum(1 for x in out if x["llmJudged"]),
        # v1.09 展示链路计数（仅统计，不参与任何判定）；论文四分型逐条展开计数
        "displayChain": {c: sum(x["displayCategory"] == c for x in out)
                         for c in ("论文", "新闻", "待定", "域外", "—")},
        "paperSubtypes": {s: sum(1 for x in out if x["typeId"] == "T01" and x["domainDisp"] != "域外"
                                 and x["displaySubcategory"] == s)
                          for s in ("综述", "研究型", "分析类", "新闻/评论/观点")},
    }
    outside = [x for x in out if x["domainDisp"] == "域外"]
    outside_summary = {
        "total": len(outside),
        "reasons": _summary_counts(outside, "outsideReason"),
        "types": _summary_counts(outside, "type"),
        "topics": _summary_counts(outside, "outsideTopic"),
        "sources": _summary_counts(outside, "src"),
    }
    write_outputs(out, stats, outside_summary)
    validate(out, stats, outside_summary)
    print(f"[direct-banding] v1.11 不设 参考/待定/忽略 类目：入域 {len(out) - len(outside)} 条直接三档，域外 {len(outside)} 条不评分")
    print(json.dumps(stats, ensure_ascii=False))


def write_outputs(items, stats, outside_summary):
    json_path = os.path.join(HERE, "semantic_results.json")
    csv_path = os.path.join(HERE, "semantic_results.csv")
    outside_csv_path = os.path.join(HERE, "域外内容分析_20260615-23.csv")
    html_path = os.path.join(HERE, "三库严格语义分类看板_20260615-23.html")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"method": "semantic-llm-calibrated-v5+three-band-scoring-v1.04+priority-tiers+s10-band-policy-v104+llm-merge+event-dedup-v105+paper-band-v106b+ref-zone-v107+future-roundup-retype-v108+display-chain-v109+doi-carrier-premise-v110+direct-banding-v111",
                   "stats": stats,
                   "outsideSummary": outside_summary, "items": items}, f, ensure_ascii=False)
    # v1.11（输出清理）：主 CSV 与移出记录 CSV 共用同一列 schema；移出件前置“移出原因”列，审计链完整可回放。
    header = ["日期", "来源", "来源内信息", "标题", "领域", "领域处置", "领域置信", "领域规则",
              "领域裁决理由", "领域证据", "次领域", "类型", "类型置信", "类型规则", "类型裁决理由",
              "类型证据", "其他满足类型", "新闻价值分/区间", "最终档位", "评分状态", "关注等级",
              "优先级层", "分区", "展示大类", "展示小类", "归入大类", "LLM语义判定", "评分卡",
              "技术路线", "路线TRL带", "TRL中位数", "权重", "原始分", "Gate后分", "封顶",
              "证据层级", "Gate动作", "缺失证据", "域外原因分组", "域外具体原因", "域外内容主题",
              "S1-S8审计", "URL/DOI", "重复数"]

    def row(x):
        return [x["date"], x["src"], x["meta"], x["title"], x["domain"], x["domainDisp"],
                x["domainConfidence"], x["domainRule"], x["domainReason"], "、".join(x["domainTerms"]),
                "、".join(x["secondaryDomains"]), x["type"], x["typeConfidence"], x["typeRule"],
                x["typeReason"], x["typeEvidence"], "、".join(x["typeAlternatives"]),
                x["valueDisplay"], x["scoreBand"], x["scoreStatus"], x["attention"],
                x["priorityTier"], x["section"], x["displayCategory"], x["displaySubcategory"],
                x["displayClass"], "是" if x["llmJudged"] else "", x["cardName"] or "",
                x["route"], x["routeTrlBand"], "" if x["trl"] is None else x["trl"],
                "" if x["weight"] is None else x["weight"],
                "" if x["scoreRaw"] is None else x["scoreRaw"],
                "" if x["scoreAfterGate"] is None else x["scoreAfterGate"],
                "" if x["cap"] is None else x["cap"], x["evidenceLevel"],
                "；".join(x["gateActions"]), "；".join(x["missingEvidence"]),
                x["outsideReason"], x["outsideReasonDetail"], x["outsideTopic"],
                " | ".join(f"{a[0]} {a[1]}：{a[2]}" for a in x["scoreAudit"]),
                x["url"] or x["doi"], x["duplicates"]]

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for x in items:
            w.writerow(row(x))

    with open(outside_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["日期", "来源", "来源内信息", "标题", "域外原因分组", "具体原因", "内容主题",
                    "新闻类型", "类型置信", "类型裁决理由", "正文质量", "URL/DOI"])
        for x in items:
            if x["domainDisp"] != "域外":
                continue
            w.writerow([x["date"], x["src"], x["meta"], x["title"], x["outsideReason"],
                        x["outsideReasonDetail"], x["outsideTopic"], x["type"], x["typeConfidence"],
                        x["typeReason"], x["contentQuality"], x["url"] or x["doi"]])

    payload = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    stats_json = json.dumps(stats, ensure_ascii=False)
    outside_json = json.dumps(outside_summary, ensure_ascii=False)
    page = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>三库严格语义分类看板 2026-06-15至23</title><style>
:root{color-scheme:light dark}*{box-sizing:border-box}body{margin:0;padding:18px;font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:light-dark(#1a1c1f,#f0f0f0);background:light-dark(#fafafa,#17181a)}
h1{font-size:20px;margin:0 0 4px}.sub{color:#888;font-size:12px;margin-bottom:14px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:14px}.stat{padding:10px 12px;border:1px solid light-dark(#ddd,#333);border-radius:10px;background:light-dark(#fff,#1e2022)}.stat b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.stat span{font-size:12px;color:#888}.stat.hi{border-color:#e8963b}.stat.hi b{color:#e8963b}.stat.click{cursor:pointer}.stat.click:hover{background:light-dark(#fff8ee,#2a2419)}
.summary-grid{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:10px;margin-bottom:14px}.summary-panel{border:1px solid light-dark(#ddd,#333);border-radius:10px;background:light-dark(#fff,#1e2022);padding:10px 12px;min-height:190px}.summary-panel h2{font-size:14px;margin:0 0 8px}.summary-list{display:grid;gap:5px;max-height:230px;overflow:auto}.sumrow{display:grid;grid-template-columns:minmax(145px,1fr) 54px;gap:8px;align-items:center;border:0;background:transparent;color:inherit;text-align:left;padding:2px 0;cursor:pointer;font:inherit}.sumrow:hover .sumname{text-decoration:underline}.sumname{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.sumval{text-align:right;font-variant-numeric:tabular-nums;color:#777}.bar{grid-column:1/-1;height:4px;border-radius:4px;background:light-dark(#eee,#333);overflow:hidden;margin-top:-4px}.bar i{display:block;height:100%;background:#e8963b}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}select,input{padding:5px 8px;border:1px solid light-dark(#ccc,#444);border-radius:8px;background:light-dark(#fff,#1e2022);color:inherit;font:inherit;min-width:118px}input[type=search]{min-width:220px;flex:1}.count{font-size:12px;color:#888;margin:6px 0}
.tablebox{overflow:auto;max-height:62vh;border-radius:10px}table{width:100%;border-collapse:collapse;font-size:13px;background:light-dark(#fff,#1e2022);min-width:1250px}th,td{padding:7px 9px;border-bottom:1px solid light-dark(#e5e5e5,#2c2e30);text-align:left;vertical-align:top}th{position:sticky;top:0;background:light-dark(#f3f4f5,#242628);cursor:pointer;user-select:none;white-space:nowrap;z-index:2}tr:hover td{background:light-dark(#f6f8fa,#26282a)}tr.sel td{background:light-dark(#eef4fb,#1e2a38)}td.tl{max-width:480px}td.tl a{color:inherit;text-decoration:none}td.tl a:hover{text-decoration:underline}.num{font-variant-numeric:tabular-nums}.small{font-size:11px;color:#888}
.badge{display:inline-block;padding:1px 7px;border-radius:99px;font-size:11px;white-space:nowrap}.b-ok{background:#dff0e2;color:#1a7a37}.b-draft{background:#fdebd8;color:#b05e12}.b-out{background:#eee;color:#777}.b-sub{background:#eef;color:#556}.b-high{background:#fbdcdc;color:#b02a2a}.b-mid{background:#fdf3d7;color:#8b6b05}.b-low{background:#eee;color:#777}
#detail{margin-top:14px;padding:12px 14px;border:1px solid light-dark(#ddd,#333);border-radius:10px;background:light-dark(#fff,#1e2022);display:none}#detail h3{margin:0 0 6px;font-size:15px}#detail .kv{display:grid;grid-template-columns:125px 1fr;gap:4px 10px;font-size:13px}#detail dt{color:#888}#detail dd{margin:0;word-break:break-word}.dims{margin:4px 0;padding-left:18px}.method{margin-top:14px;padding:10px 14px;border-left:4px solid #e8963b;background:light-dark(#fff8ee,#2a2419);font-size:12px;color:light-dark(#675f55,#b7ad9e)}.method summary{cursor:pointer;font-weight:600}
@media(max-width:1000px){.summary-grid{grid-template-columns:1fr}.cards{grid-template-columns:repeat(2,1fr)}#detail .kv{grid-template-columns:1fr}.summary-panel{min-height:0}}
</style></head><body>
<h1>三库严格语义分类看板 · 2026-06-15 – 06-23</h1>
<div class="sub">严格语义归域与类型裁决 · 02机制表价值评分 · 点击域外汇总可直接筛选，点击表头排序，点击记录查看证据</div>
<div class="cards" id="stats"></div>
<div class="summary-grid">
  <section class="summary-panel"><h2>域外原因（<span id="outside-total"></span>条）</h2><div class="summary-list" id="reason-summary"></div></section>
  <section class="summary-panel"><h2>域外新闻类型</h2><div class="summary-list" id="type-summary"></div></section>
  <section class="summary-panel"><h2>域外内容主题</h2><div class="summary-list" id="topic-summary"></div></section>
</div>
<div class="filters">
  <select id="f-src"><option value="">全部来源</option></select><select id="f-date"><option value="">全部日期</option></select>
  <select id="f-dom"><option value="">全部技术域</option></select><select id="f-type"><option value="">全部类型</option></select>
  <select id="f-disp"><option value="">全部处置</option></select><select id="f-att"><option value="">全部关注</option></select>
  <select id="f-reason"><option value="">全部域外原因</option></select><select id="f-topic"><option value="">全部域外主题</option></select>
  <input id="f-q" type="search" placeholder="搜索标题、领域、类型或裁决理由…">
</div>
<div class="count" id="count"></div>
<div class="tablebox"><table><thead><tr>
  <th data-k="date">日期</th><th data-k="src">来源</th><th>标题</th><th data-k="domainDisp">处置</th>
  <th data-k="attention">关注</th><th data-k="value">价值</th><th data-k="domain">技术域</th>
  <th data-k="type">新闻类型</th><th data-k="displaySubcategory">展示分类</th><th data-k="outsideReason">域外原因</th>
</tr></thead><tbody id="tb"></tbody></table></div>
<div id="detail"></div>
<details class="method"><summary>分类与评分口径（v1.09 机制 + v1.11 直评口径：不设 参考/待定/忽略 类目）</summary><p>默认域内：除明确域外理由外所有记录给出领域/类型划分；大模型按两份基准 docx（文献技术分类规则、新闻类型语义分类规则）语义裁决，规则层校验兜底。载体形态优先（直播→T24、N部门部署→T19）、主事件锚定（正文杂质不决定主类型）、标题阶段跃迁不落 T23。域外必须说明通读正文后排除过的语义路径及具体原因。</p><p>价值评分执行机制表S1–S8，只输出高、中、低三档；S9 优先级分层：最终档位=min(S8档位, U_type)，排序键=(优先级层P0/P1/P2, -S8分值)。S10 档位政策（v1.03）：重点瓶颈→高；一般技术类→中；投融资、不相干领域、高TRL产业动态（建厂等）、会议、宣传文案、无明确技术细节的建厂/招标/立项→低。地板：瓶颈事实(S-B01)/首创认证(S-F01)/国家重点规划题名(S-P02)/顶刊论文转载(S-P01)→高；聚焦域政策→中。上限：汽车白名单（固态/钠电/新型电池/光伏装车/直接CCUS/车网结合/智驾升阶）未中、生物医药无爆点（克隆/脑机接口/复活等）、非聚焦领域（电池/能源/零碳脱碳/AI/半导体外）、软信息与无技术细节类型→低。S-V02 信源提示分：专业编辑信源（REAI Lab、国际能源小数据等）+5（草案）。分层与档位政策不改写分数本身。</p><p><b>v1.04–v1.06 增量</b>：S10 细化（瓶颈题名锚定、招投标公告低档、首创防护、工程里程碑高地板、地方申报硬上限、市级规划防护、实质技术案例地板）；v1.05 事件级去重 C-R01/C-R03（DOI /《》文号名 / 题名 bigram Jaccard≥0.75；主记录=正文最完整·证据最高·最早发布）；v1.06 论文统一档位——S-P01v2 Nature/Science 正刊（子刊不算）→高、S-P09 题名突破锚定→最低中、S-P10 其余论文/中文转载→统一中档；v1.06b 顶刊载体语境守卫与系列文（上/下）防误并。</p><p><b>v1.07 参考区（v1.11 起停用）</b>：T02 研究报告与 T23 深度分析与评论曾单独分区、不分高中低档；2026-09-25 用户口径修订后该分区停用——T02/T23 入域后直接输出机制真实档位（S-R01 报告粗分档 / S10 政策照常），section/bandUnderlying 字段保留（恒 主榜/同档位），S1–S10 审计链不变。</p><p><b>v1.08 未来态/汇总稿/媒体解读</b>：S-A05 未来态计划硬上限——预计/将/拟×（时间）×投运·商业运营·并网 或 将在/将部署 是将来时计划（事件未发生）→ 低，首座×示范在建仍走 S-P05b 中地板；S-F02 里程碑与 S-F01 首证同步不触发；S-A04 常规发电项目汇总稿硬上限——多个/一批×新能源项目×并网/投产族（晶硅光伏/常规风电/水电等成熟技术组合）→ 低，题名点名钙钛矿/量子点/有机/海上漂浮式/单机大容量风机等低TRL新型发电技术除外；S-P02 须政策本体锚点（《》文件名×发布/印发族或国家级主体），十五五类媒体投资解读稿（出炉/定调/释放信号/投资方向）改判 T23 入参考区。</p><p><b>v1.09 展示链路与预置叶冻结</b>：展示分类＝论文（T01 四分型逐条判定：综述／研究型／分析类／新闻·评论·观点）／新闻（知识资产/工程与产业化/企业经营合作与资本/资源市场与产业链/政策法规与标准/人才与组织动态/观点与交流）＋归入大类 A科研知识·B产业化主链(链2-5)·C企业支撑·D外部环境（依据《新闻类型展示分类.xlsx》与 02 机制表《大类与产业链导航》），纯展示标注不影响 S1–S10 评分/档位/优先级；LLM 语义判定层预置叶冻结——除非与零碳产业/AI与智能科技/通用技术完全无关（域外），新闻与文献必须归入预置叶子节点/预置类型，禁止自拟"扩展:"新路径与新增节点（2026-09-24 口径）。</p><p><b>v1.11 直评口径（用户 2026-09-25 修订）</b>：不设 参考/待定/忽略 类目——入域记录一律直接按机制给出 高/中/低（T02 走 S-R01 报告粗分档、T25 经通用技术知识卡兜底、范围忽略只作审计不再拦截评分）；没进域（域外）的不评分。主输出即全集（四件套），无过滤、无额外存档件；ignored/typePending 保留为审计字段与计数。</p></details>
<script>
const DATA=__DATA_JSON__, STATS=__STATS_JSON__, OUTSIDE=__OUTSIDE_JSON__;
let sortK="date", sortAsc=true, selIdx=-1;
const $=s=>document.querySelector(s), esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const el={stats:$("#stats"),tb:$("#tb"),count:$("#count"),detail:$("#detail"),src:$("#f-src"),date:$("#f-date"),dom:$("#f-dom"),type:$("#f-type"),disp:$("#f-disp"),att:$("#f-att"),reason:$("#f-reason"),topic:$("#f-topic"),q:$("#f-q")};
function fill(sel,vals){sel.insertAdjacentHTML("beforeend",vals.filter(Boolean).map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join(""))}
fill(el.src,[...new Set(DATA.map(x=>x.src))].sort());fill(el.date,[...new Set(DATA.map(x=>x.date))].sort().reverse());fill(el.dom,[...new Set(DATA.map(x=>x.domain).filter(Boolean))].sort());fill(el.type,[...new Set(DATA.map(x=>x.type))].sort());fill(el.disp,[...new Set(DATA.map(x=>x.domainDisp))].sort());fill(el.att,[...new Set(DATA.map(x=>x.attention))].sort());fill(el.reason,OUTSIDE.reasons.map(x=>x.name));fill(el.topic,OUTSIDE.topics.map(x=>x.name));
const statDefs=[["records","去重后记录",""],["duplicates","合并重复",""],["eventMerged","事件级合并",""],["mainDomain","已归技术领域","hi"],["semanticOnly","语义/扩展域",""],["outOfScope","明确域外","hi click"],["high","高",""],["medium","中",""],["low","低",""],["p0","P0技术优先","hi"],["p1","P1产业制度",""],["p2","P2软信息后置",""],["s10Floored","S10地板升档",""],["s10Capped","S10上限降档",""],["sourceHinted","信源提示分",""],["llmJudged","LLM语义判定",""]];
el.stats.innerHTML=statDefs.map(([k,l,c])=>`<div class="stat ${c}" data-k="${k}"><b>${STATS[k]}</b><span>${l}</span></div>`).join("");
$("#outside-total").textContent=OUTSIDE.total;
el.stats.querySelector('[data-k="outOfScope"]').onclick=()=>{el.disp.value="域外";render()};
function summaryRows(target,rows,field,limit=99){const max=Math.max(...rows.map(x=>x.count),1);$(target).innerHTML=rows.slice(0,limit).map(x=>`<button class="sumrow" data-value="${esc(x.name)}"><span class="sumname" title="${esc(x.name)}">${esc(x.name)}</span><span class="sumval">${x.count} · ${x.pct}%</span><span class="bar"><i style="width:${x.count/max*100}%"></i></span></button>`).join("");$(target).querySelectorAll("button").forEach(b=>b.onclick=()=>{el.disp.value="域外";if(field==="reason")el.reason.value=b.dataset.value;if(field==="type")el.type.value=b.dataset.value;if(field==="topic")el.topic.value=b.dataset.value;render()})}
summaryRows("#reason-summary",OUTSIDE.reasons,"reason");summaryRows("#type-summary",OUTSIDE.types,"type",12);summaryRows("#topic-summary",OUTSIDE.topics,"topic");
function dispBadge(v){const c=v==="主域"?"b-ok":v==="主域(草案)"||v==="主域(语义域)"?"b-draft":v==="域外"?"b-out":"b-sub";return `<span class="badge ${c}">${esc(v)}</span>`}
function attBadge(v){const c=v==="高"?"b-high":v==="中"?"b-mid":v==="域外"||v==="低"?"b-low":"b-sub";return `<span class="badge ${c}">${esc(v)}</span>`}
function render(){const q=el.q.value.trim().toLowerCase();const list=DATA.map((x,i)=>({...x,i})).filter(x=>(!el.src.value||x.src===el.src.value)&&(!el.date.value||x.date===el.date.value)&&(!el.dom.value||x.domain===el.dom.value)&&(!el.type.value||x.type===el.type.value)&&(!el.disp.value||x.domainDisp===el.disp.value)&&(!el.att.value||x.attention===el.att.value)&&(!el.reason.value||x.outsideReason===el.reason.value)&&(!el.topic.value||x.outsideTopic===el.topic.value)&&(!q||(x.title+" "+x.domain+" "+x.type+" "+x.domainReason+" "+x.typeReason+" "+x.outsideReason).toLowerCase().includes(q)));list.sort((a,b)=>{const va=a[sortK]??-1,vb=b[sortK]??-1,c=typeof va==="number"?va-vb:String(va).localeCompare(String(vb),"zh");return sortAsc?c:-c});el.count.textContent=`显示 ${list.length} / ${DATA.length} 条${el.disp.value==="域外"?" · 域外原因与类型可继续组合筛选":""}`;el.tb.innerHTML=list.map(x=>`<tr data-i="${x.i}" class="${x.i===selIdx?"sel":""}"><td class="num">${x.date.slice(5)}</td><td>${esc(x.src)}<div class="small">${esc(x.meta).slice(0,18)}</div></td><td class="tl">${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.title)}</a>`:esc(x.title)}${x.duplicates?` <span class="badge b-out">重复×${x.duplicates}</span>`:""}</td><td>${dispBadge(x.domainDisp)}</td><td>${attBadge(x.attention)}${x.priorityTier?` <span class="badge ${x.priorityTier==="P0"?"b-ok":"b-sub"}" title="v1.02 优先级分层">${esc(x.priorityTier)}</span>`:""}${x.llmJudged?` <span class="badge b-draft" title="大模型语义判定（两份基准 docx）">LLM</span>`:""}</td><td class="num">${esc(x.valueDisplay)}</td><td>${esc(x.domain||"—")}<div class="small">${esc(x.domainConfidence)}</div></td><td>${esc(x.type)}<div class="small">${esc(x.typeConfidence)}</div></td><td>${esc(x.displaySubcategory||"—")}<div class="small">${esc(x.displayCategory||"")} · 归入${esc(x.displayClass||"—")}</div></td><td>${x.outsideReason?`<span class="badge b-out">${esc(x.outsideReason.split(" ")[0])}</span> ${esc(x.outsideReason.replace(/^O\\d+\\s*/,""))}<div class="small">${esc(x.outsideTopic)}</div>`:"—"}</td></tr>`).join("");el.tb.querySelectorAll("tr").forEach(tr=>tr.onclick=()=>show(Number(tr.dataset.i)))}
function show(i){selIdx=i;const x=DATA[i];el.detail.style.display="block";el.detail.innerHTML=`<h3>${esc(x.title)}</h3><div class="kv"><dt>来源</dt><dd>${esc(x.src)} · ${esc(x.meta)} · ${esc(x.date)} · 正文质量 ${esc(x.contentQuality)}</dd><dt>链接</dt><dd>${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.url)}</a>`:"—"}</dd><dt>领域处置</dt><dd>${dispBadge(x.domainDisp)} ${esc(x.domain||"未归域")} · ${esc(x.domainConfidence)}</dd><dt>领域规则</dt><dd>${esc(x.domainRule)}</dd><dt>领域理由</dt><dd>${esc(x.domainReason)}</dd><dt>领域证据</dt><dd>${esc(x.domainTerms.join("、")||"—")}<br>${esc(x.domainSnippet||"")}</dd>${x.outsideReason?`<dt>域外原因</dt><dd><b>${esc(x.outsideReason)}</b><br>${esc(x.outsideReasonDetail)}<br>内容主题：${esc(x.outsideTopic)}</dd>`:""}<dt>新闻类型</dt><dd>${esc(x.type)} · ${esc(x.typeConfidence)}</dd><dt>展示分类</dt><dd>${esc(x.displayCategory||"—")} · ${esc(x.displaySubcategory||"—")} · 归入${esc(x.displayClass||"—")}<div class="small">v1.09 展示链路（02机制表《大类与产业链导航》），仅展示不影响评分</div></dd><dt>类型规则</dt><dd>${esc(x.typeRule)}</dd><dt>类型理由</dt><dd>${esc(x.typeReason)}</dd><dt>类型证据</dt><dd>${esc(x.typeEvidence||"—")}</dd><dt>新闻价值</dt><dd>${esc(x.valueDisplay)} · ${esc(x.scoreBand)} · ${esc(x.scoreStatus)}${x.cardName?" · "+esc(x.cardName):""}</dd><dt>评分路线</dt><dd>${esc(x.route||"—")} · ${esc(x.routeTrlBand||"—")} · w=${x.weight??"—"}</dd><dt>Gate/缺口</dt><dd>${esc(x.gateActions.join("；")||"—")}<br>${esc(x.missingEvidence.join("；")||"")}</dd></div>${x.dimensions?.length?`<h4>评分卡维度</h4><ul class="dims">${x.dimensions.map(d=>`<li>${esc(d[0])}：${d[1]}/${d[2]} — ${esc(d[3])}</li>`).join("")}</ul>`:""}${x.scoreAudit?.length?`<h4>S1–S8审计链</h4><ol class="dims">${x.scoreAudit.map(a=>`<li><b>${esc(a[0])} ${esc(a[1])}</b>：${esc(a[2])}</li>`).join("")}</ol>`:""}`;render();el.detail.scrollIntoView({behavior:"smooth",block:"nearest"})}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortAsc=sortK===k?!sortAsc:true;sortK=k;render()});[el.src,el.date,el.dom,el.type,el.disp,el.att,el.reason,el.topic].forEach(s=>s.onchange=render);el.q.oninput=render;render();
</script></body></html>'''
    page = page.replace("__DATA_JSON__", payload).replace("__STATS_JSON__", stats_json).replace("__OUTSIDE_JSON__", outside_json)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page)


def validate(items, stats, outside_summary):
    assert items and stats["records"] == len(items)
    assert all("d" not in x and "t" not in x for x in items), "分类结果不得包含 D/T 分字段"
    assert all(x["domainRule"] and x["typeRule"] for x in items)
    assert all(date(2026, 6, 15) <= date.fromisoformat(x["date"]) <= date(2026, 6, 23) for x in items)
    outside = [x for x in items if x["domainDisp"] == "域外"]
    assert len(outside) == stats["outOfScope"] == outside_summary["total"]
    assert all(x["outsideReason"] and x["outsideReasonDetail"] and x["outsideTopic"] for x in outside)
    assert all(not x["outsideReason"] for x in items if x["domainDisp"] != "域外")
    for key in ("reasons", "types", "topics", "sources"):
        assert sum(r["count"] for r in outside_summary[key]) == outside_summary["total"], key
    # 2026-09-25 v1.11（用户口径修订）：不设 参考/待定/忽略 类目——
    # attention 只允许 高/中/低/域外；入域必有三档（T02 S-R01 粗分档 / T25 通用卡兜底）；
    # 域外＝未评分；档位计数与全集闭合；refZone/manual 审计位恒 0。
    assert all(x["attention"] in ("高", "中", "低", "域外") for x in items), "存在 参考/待定/忽略 类目残留"
    assert not any(x["section"] == "参考区" for x in items), "参考区残留（v1.11 起停用分区）"
    in_dom = [x for x in items if x["domainDisp"] != "域外"]
    assert all(x["scoreBand"] in ("高", "中", "低") for x in in_dom), "入域记录缺少 高/中/低 档位"
    assert all(x["attention"] == x["scoreBand"] for x in in_dom), "入域记录 attention 与档位不一致"
    assert all(x["scoreBand"] == "未评分" and x["value"] is None and x["attention"] == "域外"
               for x in items if x["domainDisp"] == "域外"), "域外记录不应携带评分"
    assert stats["high"] + stats["medium"] + stats["low"] + stats["outOfScope"] == len(items), "档位计数不闭合"
    assert stats["refZone"] == 0 and stats["manual"] == 0, "参考/待定 审计位应为 0"
    # 2026-09-24 v1.09：展示链路一致性——每条记录带展示标注；域外标“域外”；计数闭合；映射完备。
    assert all(x["displayCategory"] and x["displaySubcategory"] and x["displayClass"]
               for x in items), "展示链路字段缺失"
    assert all((x["displayCategory"], x["displaySubcategory"]) == ("—", "域外")
               for x in items if x["domainDisp"] == "域外"), "域外记录展示分类应为 域外"
    assert all(x["displayCategory"] != "域外" for x in items if x["domainDisp"] != "域外")
    assert sum(stats["displayChain"].values()) == len(items), "displayChain 计数不闭合"
    assert all(x["typeId"] in DISPLAY_CHAIN_MAP for x in items if x["domainDisp"] != "域外"), \
        "DISPLAY_CHAIN_MAP 未覆盖出现的类型"
    # v1.09 论文四分型：域内 T01 小类必须为四值之一，且计数与 displayChain.论文 闭合
    assert all(x["displaySubcategory"] in ("综述", "研究型", "分析类", "新闻/评论/观点")
               for x in items if x["domainDisp"] != "域外" and x["typeId"] == "T01"), "论文四分型小类非法"
    assert sum(stats["paperSubtypes"].values()) == stats["displayChain"]["论文"], "paperSubtypes 计数不闭合"
    for fn in ("semantic_results.json", "semantic_results.csv", "域外内容分析_20260615-23.csv",
               "三库严格语义分类看板_20260615-23.html"):
        assert os.path.getsize(os.path.join(HERE, fn)) > 100


if __name__ == "__main__":
    build()

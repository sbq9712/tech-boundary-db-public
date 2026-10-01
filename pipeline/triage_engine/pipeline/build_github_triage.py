# -*- coding: utf-8 -*-
"""三 GitHub 库 2026-06-15..06-23 内容按 v0.96 规则初筛分类 + HTML 检查看板。

规则来源（与三簿同源，零手工转录）：
  S1 领域 D —— 03 域卡②判定词表（JSON domain_cards core/ext/actors + expand_domains_data 24 草案域）
  S2 类型 T —— 01《关键词模式表》机器层：TYPES 触发词正则 + as_is 19 评价族正则
  选卡      —— TYPES.card（12 张通用卡）
文献补丁（2026-09-11，针对文献库英文题录漏分）：
  · lit_rules_data.py（parse_lit_rules_docx.py 从 framework/文献技术分类规则_行业图景版.docx 生成）
    的 125 叶典型英文术语按 叶→域 并入 D 计分核心词档，同公式同阈值，仅 src=literature 生效
  · 英文匹配：词边界 + 复数容错(s/es/ies) + 空格/连字符互换；补丁命中证据带 ※ 前缀
  · 另输出叶级"文献分类路径"证据（可落 E99/暂不建叶，仅展示不改域归属）
  · 题名对象优先（docx 一·3"研究对象优先"）：挂域叶术语命中题名 → 该叶映射域直判主域，
    公式 D 分与原最优域降为次高域/证据；仅正文命中时仍按公式处置
  · 差异分析见同目录《文献补丁差异报告.md》
简化口径（看板"方法说明"中明示，非正式 RecordScore）：
  · 指标三要素简化：数值+域单位=15 / 数值+通用单位=7
  · 主体只判"∈域主体清单 15"（供应链 8 分档未拆）
  · 载体先验简化为来源先验 +10（文献库→科研类类型；新闻/公众号→产业类类型）
  · 正文词表扫描截前 2500 字
评分修订（2026-09-11，用户复核反馈）：
  · 事件动词分层：建成投运类=15 / 商务前期类(开工/签约/中标/招标/发布等)=8 / 拟建将建再降至 5
  · 近似同事件合并：新闻/公众号源（含跨源转载）±5 天 + 同域 + 标题 bigram Dice≥0.60
    （纯英文题名 0.72；双方数字集无交集视为不同事件不并），保留关注档高、D 高者
评分卡机器层（2026-09-11 三次修订，替代同日删除的"关注分 A"——A 仅 D/T 线性加总无信息量）：
  · 选卡：TYPES.card 主卡（T15 资源体系 card_resource 未建卡、T25 待定 → 无卡转人工，显示"待定"）
  · 维度初判：按 02 簿 family_cards 各维度分档做机器近似（达基线/超基线幅度不可判：
    数值+域单位≈达基线档，首发/纪录词+域单位≈突破档；主体一线/二线、金额异常度、
    轮次阶段匹配均为词面近似——简化限制全部在看板方法说明⑥明示）
  · Gate 封顶：按各卡 gate 机器化（宣传性发布≤40、仅意向≤35、金额未披露≤50、
    无数值无基期≤30、仅宣布≤45、TRL8-9 常规运行通报≤30×权重等）
  · TRL 加权：A/B 组卡乘 TRL 权重（trl_framework：TRL1-3=1.0 → TRL9=0.85，
    按检测词+中文阶段动词初判，未判按 1.0）；C 组（商务/制度类）不乘
  · D01 成熟晶硅路线（TOPCon/PERC 且无钙钛矿/叠层）封顶 79（用户 09-11 复核）
  · 档位门槛：卡分 S≥80 高 / 60–79 中 / <60 低（02 簿只钉死"≥90 稀缺档须 Gate 全过"；
    80/60 为看板初筛展示阈值，常数待回测）；参评=处置 主域/主域(草案)/次域候选，
    弱相关与域外不评级；无卡类型待定不评级
评分卡修订（2026-09-11 五次修订·S3 组，项目/生产/产品/验证四卡校准）：
  · 卡内数值兜底：中文工程单位（兆瓦/万吨/亿元…NUM_CARD_R）计入"有数值披露"，
    防规模/性能/规格维度误判无数值、Gate 无数值类误触发（不动 score_domain 的 D 分口径）
  · E 草案域规模兜底：草案域 units 多为 %/h/℃ 性能锚，其条目"数值+通用规模单位"
    （万吨/GWh/兆瓦…）在规模/性能维度按"≈达基线"15 档计（原 8 分档）
  · card_project 阶段跃迁扩为 35/25/22/18/12/5：补"交付"强事件；新增验证里程碑 22 档
    （试飞/载人/路试/示范运行/完成试验/市场进入）与投资落定 18 档；工程确定性 20 档补
    "投产/交付事实已发生"（原 4 档"仅宣布"+Gate≤45 误伤投产稿）；新增施工动态（开工/吊装
    无投运证据）封顶 75；强事件正文检索窗 600→1000 字、将来时抑制补计划/可能/有望
  · card_product 阶段阶梯 30 档补"道路测试"、26 档补"市场进入"；card_validation 词面补
    ASTM/IEC（第三方档）、联合/共同/协同开发（联合验证档）、试点（中试档）
分型消歧补丁（2026-09-11 四次修订，规避新闻"发布"类动词致 T 分型随机性）：
  · ①动宾联判：发布类动词+报告对象词 → T02（题名《…报告/皮书》同；题名只有发布动词时
    认正文前段《…报告》书名号证据——水规总院"重磅发布"类稿）；产品对象不经覆写（T09 自然胜出）
  · ②题名招标/中标证据 → T18（题名已 T08/T18 者不覆写；仅认题名证据，
    防复合题名"EPC 招标"段误路由走 T08 的项目稿）
  · ③来源先验证据化：非文献源正文含论文证据（DOI/课题组/期刊）→ 产业先验换科研先验，
    且 argmax∈{T09,T08,T24} 时覆写→T01（公众号转述论文稿不再被推向产品类）
  · ④近分双候选：T 最高与次高分差 <10 → 低置信标记（显示次高候选，不强行 argmax）；
    仅 sc≥35（次型及以上）生效——待定/域外条目各类型普遍同分 0，标记无意义
  · ⑤同事件类型分歧：近似同事件合并组内类型不一致 → 类型分歧标记转人工
  · ⑥回归闭环：typing_regression_cases.json + check_typing_regression.py 固化已知分型判例
分型修订（2026-09-11 五次修订·S1 组，用户复核 28 条反馈之 #1/#7/#8/#9/#10/#11/#12/#16/#18/#19/#20/#22）：
  · 触发词运行层补充 TYPE_TRIG_EXT：01 簿部分 T 型触发词缺失（定增→T13、政策文件特征→T19、
    标准特征→T20、招聘→T21、趋势/工艺解读→T23、会议→T24、项目公示/吊装/可研→T08），
    与既有触发词同公式计分（标题 40 / 正文 25），不改三簿数据文件（回写建议见 S1 report）
  · T01 正文触发词证据化：非文献源正文泛词（实验/表征/样品/对比——会议预告模板"设备、样品、
    资料"、材料文"表征材料"、机构名"XX实验室"即可命中）不再单独计 fam25，须论文载体证据
    （PAPER_EV_R 或题名顶刊书名号《Nature/Science/…》）联判（#7/#10 误判 T01 根因）
  · 消歧⑦周刊/合辑类汇总稿（题名正则）→ T25 聚合源标题流（转人工/免评候选，#20）；
    main 层同步留 digest 标记供 S5 对接处置/免评机制
  · 消歧⑧题名会议/活动证据（研讨会/评审会/召开…）→ T24，压过 T08"预可研"等字面（#11）
  · 消歧⑨期刊论文全文转载稿（题名《刊名》文章 / 正文"引用本文+DOI"）→ T01，
    压过 T02 泛触发词"展望/综述"（#8 期刊论文误判 T02 根因）
域判定修订（2026-09-11 五次修订·S6 组，D 域归属/正文预处理）：
  · 正文预处理 strip：截断(前2500字)后剥离两类明确杂质——尾部栏目/推广段（相关阅读/
    延伸阅读/往期回顾/关注我们/项目数据库精选/赞助项目介绍 等 12 类标记词，须出现在文末
    1/4 后才截尾）与穿插的会展广告段（『20XX+名称+论坛/峰会/…+将于X月X日在X召开』起至最近
    『等。』，题名本身是会议报道时不剥）；环境变量 S6_DISABLE_STRIP=1 可关（A/B 扫描用）
  · D01 LED 负条件：题名含 LED/发光二极管/电致发光/light-emitting/electroluminescen 等
    LED 侧词且题名无 solar/photovoltaic/光伏/太阳能（正文残留光伏词视为背景/展望）→ D01
    计分清零；题名含光伏侧词一律不压（钙钛矿太阳能电池/叠层光伏不被误杀）；36 域无光电器件/
    半导体域可路由（EXPAND_DOMAINS 已核查）→ 按词面降域外，待"新建光电器件域"（工作簿建议）
  · 主体/目的优先（载体→主体小表 SUBJECT_PRIORITY）：题名含『载体+制X』复合动宾（如
    海上风电制氢）或（题名+正文前600字 载体词∧主体词同现 且 主体域核心词证据≥载体域 且
    scope 含制X动宾）且主体域 D≥40、公式最优域∈载体域 → 主域改判主体域，公式最优域降次高
  · 次高域证据门槛：次高域须 题名核心/扩展词命中 或 正文核心词命中≥2；仅主体清单撑起
    （如综合能源集团『国家电投』同报 D07 核电）或仅正文扩展词命中的域不再展示为次高域
文献评分+媒体转述合并修订（2026-09-11 五次修订·S2 组）：
  · card_tech"证据质量"双通道：文献=期刊档位表（顶档 Nature/Science/Cell 及子刊=20、
    高档 Joule/EES/AM/Angew/JACS/PNAS 系=16、普通 SCI(有 DOI)=12、预印本=6，分值 TODO(回测)）；
    非文献"媒体转述论文"（题名顶刊词或正文 DOI/期刊证据 + 题名非原创产业事件）→
    顶刊转述 20 / 普通期刊转述 12 / 无证据 6——公式 证据质量 = f(期刊档, 媒体转述, DOI)
  · 通讯作者被引量：RSS 摘要拿不到，预留 author_cite 输入位（None=不调整），不编造数据
  · 综述/观点路由：题名 review/perspective/outlook/roadmap/综述/展望 → 走期刊档位通道
    （指标表现固定 6、新颖性 8），不采瓶颈参数
  · 文献 first_evid 英文扩展：record-breaking/world record/record efficiency/unprecedented
    （题名或摘要前 600 字）→ 突破档 25；媒体转述通道纪录词亦可出自正文前 600 字
  · 媒体转述指标档：纪录/首发词+通用单位数值+量化对比声明（翻了N倍等）→ 20（自报超基线，TODO(回测)）
  · TRL 初判守卫："单位重量产生的功率"类跨词"量产"误判 TRL8 → 量产 加 (?<!重) 负断言
  · 跨源文献×媒体报道合并（反馈 #4）：①DOI 直配（正文/URL 含 DOI 与文献库 doi 规范化全等）
    ②英文题名直配（《英文题名》引述或整题包含，词集 Dice≥0.80+公共词≥4+同域+±5 天，保守阈值）
    → 媒体条目并入文献条目（显示"媒体报道×N"）；文献条目获媒体加分（权威媒体
    新华社/科技日报/央视/人民日报 +5/条、其他 +2/条、累计封顶 +8，TODO(回测)，卡分封顶 100）；
    并入证据升档：媒体报道含纪录/首发词+域单位 → 指标表现→25、含机理/重构词 → 新颖性→25；
    中文转述无法直配的不合并（后续方案见 report）
"""
import csv
import glob
import json
import os
import re
import sys
import html as _html
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
# triage_engine 打包版（2026-09-23 v1.07）：规则单源随包分发（../rules/），不依赖 outputs 相对层级；
# 与 outputs/github-triage-20260615-23 运行层同源快照，机制与表格内容一致。
RULES = os.path.normpath(os.path.join(HERE, "..", "rules"))  # 包根/rules（一级上溯；两级会指到包外，2026-09-23 修正）
sys.path.insert(0, HERE)
sys.path.insert(0, RULES)
from cls_data import TYPES  # noqa: E402
from expand_domains_data import EXPAND_DOMAINS  # noqa: E402
from lit_rules_data import LIT_LEAVES  # noqa: E402

# trl_scoring_data 定位修订（2026-09-11 五次修订·S1 组）：原 RULES 相对上溯两级仅适配主目录
#   outputs/github-triage-*；沙箱 outputs/triage-review-20260911/S1-typing 层级更深导致 FileNotFoundError。
#   改为从 HERE 向上搜索含 .claude/worktrees/trl-rules 的仓库根，两层目录均可运行（通用化，无绝对路径硬编码）。
def _repo_root(start):
    d = start
    for _ in range(6):
        if os.path.isdir(os.path.join(d, ".claude", "worktrees", "trl-rules")):
            return d
        d = os.path.dirname(d)
    return start
# triage_engine 打包版：优先用随包 rules/trl_scoring_data.json；开发仓内回退原 .claude/worktrees 路径。
_BUNDLED_TRL_JSON = os.path.join(RULES, "trl_scoring_data.json")
JSON_PATH = _BUNDLED_TRL_JSON if os.path.exists(_BUNDLED_TRL_JSON) else os.path.join(
    _repo_root(HERE), ".claude", "worktrees", "trl-rules",
    "outputs", "trl-weighted-scoring-rules-20260908", "trl_scoring_data.json")
D = json.load(open(JSON_PATH, encoding="utf-8"))

# triage_engine 打包版：原始抓取根目录改为环境变量可配（引擎调用时不使用 read_rows，此值仅直跑脚本用）。
SRC_ROOT = os.environ.get("TRIAGE_SRC_ROOT",
                          r"D:\ADV knowledge database\tech-knowledgebase-builder\data\downloads\github")
W0, W1 = date(2026, 6, 15), date(2026, 6, 23)
BODY_CAP = 2500

# 2026-09-12 范围规则：仅当题名独立分句以宁德时代/CATL 起句时，才认定其为主要主体并免评。
# 正文提及、合作方/供应商/产业链等关系词不触发，避免按品牌词误杀。
CATL_MODIFIER_R = re.compile(
    r"^(?:宁德时代|CATL)\s*(?:供应商|概念股|产业链|股东|合作方|客户|订单|相关公司)", re.I)
TITLE_CLAUSE_SPLIT_R = re.compile(r"[，,。；;：:！!？?｜|—–]+")


def catl_scope_ignore_reason(item):
    """只用题名语法判断 CATL 是否为主要主体，保证范围过滤可审计。"""
    title = re.sub(r"^[\s\"'“”‘’【】\[\]]+", "", str(item.get("title") or ""))
    for clause in TITLE_CLAUSE_SPLIT_R.split(title):
        clause = re.sub(r"^[\s\"'“”‘’【】\[\]]+", "", clause)
        if not re.match(r"^(?:宁德时代|CATL)(?:\b|(?=[\u4e00-\u9fff]))", clause, re.I):
            continue
        if CATL_MODIFIER_R.search(clause):
            return ""
        return "范围免评:题名独立分句以宁德时代/CATL起句，判为主要主体（仅题名语法，不采正文提及）"
    return ""

# 正文域清洗（2026-09-11 五次修订·S6 组）：只处理可明确识别的尾部栏目/推广段。
# 阈值仅用于防止把正文开头同名小标题误当尾注；TODO(回测)：300 字。
TRAILING_NOISE_R = re.compile(
    r"往期(?:精彩)?回顾|推荐阅读|相关阅读|延伸阅读|更多(?:精彩|内容)|关注我们|扫码关注|"
    r"项目数据库精选|会议赞助项目介绍|免责声明|版权声明")
CONFERENCE_TITLE_R = re.compile(r"会议|论坛|峰会|大会|博览会|展览会|研讨会|评审会|审查会")
CONFERENCE_PROMO_R = re.compile(
    r"20\d{2}.{0,42}?(?:论坛|峰会|大会|博览会|展览会|研讨会).{0,30}?"
    r"将于\s*\d{1,2}\s*月\s*\d{1,2}\s*日.{0,18}?召开")


def preprocess_body(body, title):
    """剥离明确尾注/会展推广，返回（清洗后正文，审计理由）。

    可用 S6_DISABLE_STRIP=1 做 A/B 回测。会议稿本身不应用“会展推广”截断，
    但仍可清理其末尾的推荐阅读等栏目噪声。
    """
    raw = str(body or "")
    if os.environ.get("S6_DISABLE_STRIP") == "1":
        return raw[:BODY_CAP], ""
    cuts = []
    for m in TRAILING_NOISE_R.finditer(raw):
        if m.start() >= 300:  # TODO(回测)：尾注最早截断位置 300 字
            cuts.append((m.start(), "尾部栏目/推广:" + m.group(0)))
            break
    if not CONFERENCE_TITLE_R.search(title):
        m = CONFERENCE_PROMO_R.search(raw)
        if m and m.start() >= 300:  # TODO(回测)：正文中会展广告最早截断位置 300 字
            cuts.append((m.start(), "穿插会展推广:" + m.group(0)[:36]))
    if cuts:
        pos, why = min(cuts, key=lambda x: x[0])
        return raw[:pos].rstrip()[:BODY_CAP], why
    return raw[:BODY_CAP], ""

# ---------------- 词表装载（36 域） ----------------
def _terms(s):
    return [w.strip() for w in str(s).split("|") if w.strip()]

def _actors(s):
    out = []
    for a in re.split(r"[、|，,]", str(s)):
        a = re.sub(r"（[^）]*）|\([^)]*\)", "", a).strip()
        if a:
            out.append(a)
    return out

DOMS = []
for i, dc in enumerate(D["domain_cards"]):
    DOMS.append({"no": f"D{i+1:02d}", "id": dc["domain_id"], "name": dc["domain"],
                 "status": "confirmed",
                 "core": _terms(dc["core_terms"]), "ext": _terms(dc.get("ext_terms", "")),
                 "actors": _actors(dc["actors"]),
                 "units": [m.get("unit") for m in dc.get("metrics", []) if m.get("unit")]})
for e in EXPAND_DOMAINS:
    DOMS.append({"no": e["id"], "id": e["id"], "name": e["name"], "status": "draft",
                 "core": _terms(e["core"]), "ext": _terms(e.get("ext", "")),
                 "actors": _actors(e["actors"]),
                 "units": [u for _m, u, _r in e.get("metrics", []) if u]})
DOM_NO = {d["id"]: d["no"] for d in DOMS}
DOM_BY_NO = {d["no"]: d for d in DOMS}

def _matcher(term):
    if re.fullmatch(r"[A-Za-z0-9 .+-]+", term):
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)
    return re.compile(re.escape(term), re.I)

for d in DOMS:
    d["core_r"] = [(_t, _matcher(_t)) for _t in d["core"]]
    d["ext_r"] = [(_t, _matcher(_t)) for _t in d["ext"]]
    d["actors_r"] = [(_t, _matcher(_t)) for _t in d["actors"]]

# 题名中的“专属技术路线”比主体名或一个孤立数值更能说明领域归属。原 D 公式题名最高仅 40，
# 无主体清单、无域单位时，即使“二氧化碳储能/海水制氢”等对象写在题名中也只能落次域候选。
# 这里增加可审计的专属路线证据（25 分）；只列跨域歧义很低的复合术语，单独“储能/制氢/电池”不计。
# TODO(回测)：词表扩充必须逐域提供反例，不能直接把全部 core_terms 当成专属路线。
DOMAIN_ROUTE_R = {
    "D02": re.compile(r"超高镍(?:正极|层状氧化物)|锂硫电池|锂金属电池|固态锂电池|硅碳负极", re.I),
    # v0.97 D-G03：专属子域优先于宽泛 D03。专属词只给对应域加路线分；D03 不再
    # 通过“储能”父类反向覆盖 E11/E12/E14/D08。
    "D08": re.compile(r"压缩空气储能|CAES|(?:近等温|压缩|液态)二氧化碳(?:电池|储能)|"
                       r"二氧化碳电池|液态空气储能", re.I),
    "E11": re.compile(r"全钒液流|铁铬液流|锌溴液流|液流电池|flow battery", re.I),
    "E12": re.compile(r"熔盐储热|molten salt thermal storage|相变储热|热化学储热", re.I),
    "E14": re.compile(r"重力储能|飞轮储能|抽水蓄能", re.I),
    "D05": re.compile(r"海水(?:直接)?制氢|碱性电解槽|PEM电解槽|AEM电解槽|绿氢制甲醇|"
                       r"电解水制氢|风光氢氨醇", re.I),
    "E03": re.compile(r"生物甲烷|生物质(?:制|气化).{0,8}(?:甲醇|燃料|天然气)", re.I),
}

# ---------------- 文献英文召回层（docx 文献分类规则补丁，仅 src=literature 生效） ----------------
def _en_matcher(term):
    """英文词组匹配：词边界（防 gas 命中 gasket）＋ 复数容错(s/es，辅音+y→ies)
    ＋ 空格/连字符互换（lithium-ion ↔ lithium ion）。"""
    toks = [re.escape(t) for t in term.split()]
    body = r"[\s\-]+".join(toks)
    if re.search(r"[^aeiou]y$", term):
        body = body[:-2] + r"(?:y|ies)"
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?:s|es)?(?![A-Za-z0-9])", re.I)

LEAF_RX = [{"leaf": lf["leaf"], "path": lf["path"], "target": lf["target"],
            "rx": [(t, _en_matcher(t)) for t in lf["en"]]} for lf in LIT_LEAVES]
# 叶→域并入：同一域多叶术语去重后作为该域补丁核心词（证据词带 ※ 前缀）
DOM_LIT = {}
for _lf in LEAF_RX:
    if _lf["target"] in (None, "E99"):
        continue
    _seen = {t for t, _rx in DOM_LIT.get(_lf["target"], [])}
    for _t, _rx in _lf["rx"]:
        if _t not in _seen:
            DOM_LIT.setdefault(_lf["target"], []).append((_t, _rx))
            _seen.add(_t)
for d in DOMS:
    d["lit_r"] = [("※" + _t, _rx) for _t, _rx in DOM_LIT.get(d["no"], [])]

def best_leaf(item, ds=None):
    """文献分类路径证据：返回最佳命中叶（全树）＋ 域内叶（挂 D/E 域者，可与之不同）。
    排序键：题名命中数 > 题名+正文 > 该叶映射域 D（同分时挂域叶优先于暂不建叶）> 更深路径。"""
    ds = ds or {}

    def _scan(only_mapped):
        best = None
        for lf in LEAF_RX:
            if not lf["rx"] or (only_mapped and lf["target"] in (None, "E99")):
                continue
            th = sum(len(rx.findall(item["title"])) for _t, rx in lf["rx"])
            bh = sum(len(rx.findall(item["body"])) for _t, rx in lf["rx"])
            if th + bh == 0:
                continue
            terms = [t for t, rx in lf["rx"]
                     if rx.search(item["title"]) or rx.search(item["body"])]
            key = (th, th + bh, ds.get(lf["target"], 0), -lf["path"].count(">"))
            if best is None or key > best[0]:
                best = (key, lf, terms[:5], th, bh)
        return best

    anyb = _scan(False)
    if anyb is None:
        return None
    _k, lf, terms, th, bh = anyb
    out = {"leaf": lf["leaf"], "path": lf["path"], "target": lf["target"],
           "terms": terms, "t": th, "b": bh}
    inb = _scan(True)
    if inb is not None and inb[1]["leaf"] != lf["leaf"]:
        _k2, lf2, terms2, th2, _bh2 = inb
        out["inleaf"], out["inpath"], out["intarget"], out["interms"] = \
            lf2["leaf"], lf2["path"], lf2["target"], terms2
        out["int"] = th2
    return out

UNITS_GENERIC = ["%", "％", "亿", "万", "MW", "GW", "GWh", "MWh", "kWh", "Wh/kg", "mAh", "g/kWh",
                 "km", "小时", "循环", "倍", "°C", "MPa", "bar", "nm", "μm", "美元", "欧元", "元"]
NUM_UNIT_R = re.compile(r"\d+(?:\.\d+)?\s*(?:" + "|".join(re.escape(u) for u in UNITS_GENERIC) + ")",
                        re.I)
# 评分卡修订（2026-09-11 五次修订·S3 组）：卡内本地数值兜底正则（不动全局 UNITS_GENERIC /
#   score_domain——域分轨归 S6）：新闻稿中文工程单位（兆瓦/万吨/亿元/℃…）不认会导致
#   "规模/性能/规格"维度误判无数值、Gate 无数值类误触发。仅 score_card 层使用。
UNITS_CARD_EXTRA = ["兆瓦时", "兆瓦", "万千瓦时", "万千瓦", "千瓦时", "千瓦", "万吨级", "万吨", "万立方米",
                    "平方公里", "亿元", "万元", "亿", "公斤", "吨", "公里", "英里", "磅", "桶", "加仑",
                    "升", "米", "℃", "°C", "克", "MPa"]  # 度量单位，不含台/组/户/年等计数单位 TODO(回测)
NUM_CARD_R = re.compile(r"\d+(?:\.\d+)?\s*(?:" + "|".join(re.escape(u) for u in
                                                          list(dict.fromkeys(UNITS_GENERIC + UNITS_CARD_EXTRA))) + ")",
                        re.I)
# 规模类单位（可锚定"规模×域量级"档的量纲；%/℃/循环等性能类不算规模）
UNITS_SCALE_CARD = ["万吨级", "万吨", "万立方米", "兆瓦时", "兆瓦", "万千瓦时", "万千瓦", "千瓦时", "千瓦",
                    "MW", "GW", "GWh", "MWh", "kWh", "kW", "Wh/kg", "mAh", "平方公里", "公里", "吨",
                    "公斤", "桶", "亿", "万", "美元", "欧元", "元"]  # TODO(回测)
NUM_SCALE_R = re.compile(r"\d+(?:\.\d+)?\s*(?:" + "|".join(re.escape(u) for u in UNITS_SCALE_CARD) + ")",
                         re.I)
# 事件动词分层（2026-09-11 评分修订）：建成投运类=强(15)，商务前期类=弱(8)，拟建/将建再降
STAGE_STRONG_R = re.compile(
    r"投产|量产|并网|投运|交付|下线|建成|封顶|点火|爬坡|commercializ|mass produc|grid.?connect|"
    r"ship(?:ped|ment)|deliver|commission(?:ed)?", re.I)
STAGE_WEAK_R = re.compile(
    r"开工|奠基|签约|中标|获批|备案|公示|招标|采购|收购|破产|退出|上市|发售|推出|扩产|发布|"
    r"完成.{0,6}轮|launch|start(?:s|ed)? up", re.I)
FUTURE_R = re.compile(r"拟建|拟新建|拟投资|将建|计划建设|规划建设|规划中|即将|预计")
RESEARCH_NAME_R = re.compile(r"论文|研究|综述|建模|专利|知识|观点")
INDUSTRY_NAME_R = re.compile(r"产品|项目|企业|融资|市场|政策|订单|采购|供应|人才|经营|验证|生产|示范|行情")

# 类型触发词正则（01 各 T sheet ② 具体特征）
TYPE_TRIG = {}
for t in TYPES:
    tt, bt = [], []
    for row in t.get("features", []):
        cat, pat = row[0], row[1]
        try:
            rx = re.compile(pat, re.I)
        except re.error:
            continue
        if cat == "标题触发词":
            tt.append(rx)
        elif cat == "正文触发词":
            bt.append(rx)
    TYPE_TRIG[t["id"]] = (tt, bt)

# ---- 触发词运行层补充（2026-09-11 五次修订·S1 组）------------------------------------
# 01 簿《关键词模式表》部分 T 型触发词缺失/过泛（用户复核 #7 定增→T13、#9/#19 政策文件特征→T19、
# #16 标准特征→T20、#10d 招聘→T21、#10a/#10c/#22 趋势吹风/工艺解读稿→T23、#11 会议→T24、
# #1/#10b/#12 项目公示/吊装/可研→T08）。与既有触发词同公式计分（标题命中 40 / 正文命中 25），
# v0.97 已同步回 classification-scoring-rules-20260909 数据源与三份机制工作簿。
# 模式设计为通用词面（无 URL/主体硬编码）；新增词档位与既有簿面同权，常数无需回测。
TYPE_TRIG_EXT = {
    # T01：用户反馈 #22 将“主流生产工艺：…”作为技术论文/文章处理；限定题名结构，避免正文泛词误吸
    "T01": ([r"(?:主流|典型|常用)?生产工艺[：:]"], []),
    # T08：项目前期公示与工程节点（01 簿有"开工/建成/EPC"但缺公示/吊装/可研阶段词）
    "T08": ([r"项目公示|(?:社会稳定风险|环评|选址|用地|核准|备案)(?:信息)?公示|可行性研究|预可研|可研|概念研究"],
            [r"完成吊装|首台[^，。\n]{0,16}(?:吊装|安装)|海上安装|主体工程施工|试桩|全容量投产|社会稳定风险评估公示"]),
    # T07：真实环境/整机验证节点；比“团队/宣布”等泛词更能说明事件实质
    "T07": ([r"道路测试|路测|实车测试|整车测试|真实工况测试|示范验证"],
            [r"正式启动道路测试|开发测试车|真实使用环境下.{0,20}验证|"
             r"试点装置.{0,30}(?:持续|运行)|持续.{0,20}试点装置|"
             r"完成.{0,50}(?:试验|验证)|试验.{0,60}试点装置"]),
    # T09：既有产品跨入明确市场/开始销售，属于产品商业化状态而非科研计划
    "T09": ([r"产品.{0,12}(?:进入|登陆|进军|落地).{0,15}市场|产品.{0,8}(?:上市|销售)"], []),
    # T13：股权/再融资动词（01 簿有"增发"但漏"定增"这一简写主形态，#7）
    "T13": ([r"定增|拟募|募集|配股|增资"], []),
    # T19：政策文件结构特征（部门联合发文/行动方案/新政/文号；01 簿触发词未覆盖简写与文号）
    "T19": ([r"新政|[一二三四五六七八九十\d]+个?部门|(?:三年|攻坚|专项|试点)行动|行动方案|行动计划|实施方案|"
             r"征求意见|印发|施行|《[^》]{2,40}(?:通知|方案|办法|意见|规划|纲要|计划)》"],
            [r"等部门|[一二三四五六七八九十\d]+个?部门联合|〔\d{4}〕\s*\d+号|联合印发|联合发布《"]),
    # T20：标准/认证/准入（#16"分级标准"无任何 T20 簿面词命中）
    "T20": ([r"分级标准|行业标准|国家标准|团体标准|国际标准|强制性(?:国标|标准)|"
             r"标准(?:体系|征求意见|发布|立项|实施|出台|将|重塑)|准入|认证规则"], []),
    # T21：招聘启事（01 簿触发词全是人事变动，漏招聘场景，#10d）
    "T21": ([r"招聘|博士后|诚聘|应聘|启事|招贤"], []),
    # T23：媒体趋势吹风稿/工艺解读稿（#10a/#10c 万亿风口、入局；#22 生产工艺科普）
    "T23": ([r"风口|万亿(?:级|市场)|赛道|蓝海|入局|抢滩|竞逐|争夺战|大洗牌|"
             r"工艺流程[：:]|一文读懂|一文了解|技术科普|科普\s*[|｜]|"
             r"数据中心.{0,24}(?:用电|电力|能源|复兴|关键答案|脱碳)|"
             r"(?:水泥|钢铁|化工|航运|航空).{0,16}(?:AI|人工智能)|"
             r"(?:AI|人工智能).{0,16}(?:水泥|钢铁|化工|航运|航空)"], []),
    # T24：会议/活动（01 簿有"大会/峰会/论坛"但漏研讨会/评审会/召开等，#11）
    "T24": ([r"研讨会|评审会|交流会|座谈会|(?<!股东)大会|年会|博览会|展览会|论坛|发布会|召开|举办"], []),
}
for _tid, (_tpats, _bpats) in TYPE_TRIG_EXT.items():
    _tt, _bt = TYPE_TRIG[_tid]
    _tt.extend(re.compile(p, re.I) for p in _tpats)
    _bt.extend(re.compile(p, re.I) for p in _bpats)

FAM_PATTERNS = [(k, re.compile(v, re.I)) for k, v in D["as_is"]["family_patterns"].items()]
TYPES_BY_ID = {t["id"]: t for t in TYPES}

# ---------------- 分型消歧补丁（2026-09-11 四次修订，规避新闻分型主观随机性，方法说明②） ----------------
# ①动宾搭配条件触发：『发布』类动词单独出现不再直接指向 T09，须与对象词联判——
#   发布+报告对象→T02；题名《…报告/皮书》→T02；题名只有发布动词时，正文前段
#   《…报告》书名号证据亦认（水规总院"重磅发布"类稿，正文才是真对象）；
#   发布+型号/产品对象→T09（不经覆写，argmax 自然胜出）
# ②正文证据覆写：招标编号/中标公示类证据→T18（无论题名营销词）；题名分到产品/项目/会议但
#   正文是论文证据（DOI/课题组/期刊）→T01（公众号转述论文稿不再被产业先验推向产品类）
# ③来源先验证据化：新闻/公众号正文含论文证据时，产业先验 +10 替换为科研先验 +10（不再硬偏置）
# ④近分双候选：T 最高与次高分差 <10 → 标"低置信"（显示次高候选，不强行 argmax 掩盖）
# ⑤同事件类型分歧：近似同事件合并组内类型不一致 → 主记录打"类型分歧"标记转人工
PUB_VERB_R = re.compile(r"发布|公布|推出|发表|印发|出台")
REPORT_OBJ_R = re.compile(r"报告|白皮书|蓝皮书|绿皮书|年报|盘点|一图读懂|榜单|名单|排名|指数|宣言|皮书")
REPORT_TITLE_R = re.compile(r"《[^》]{2,28}?(?:报告|白皮书|蓝皮书|绿皮书|皮书|指南)")
BID_EV_R = re.compile(r"招标编号|招标公告|中标公示|中标候选人|中标结果|成交公告|开标|评标|投标|预中标")
RECRUIT_TITLE_R = re.compile(r"招聘|博士后|诚聘|应聘|启事|招贤|职位|岗位要求", re.I)
FINANCE_TITLE_STRONG_R = re.compile(
    r"融资|完成.{0,8}[A-E]\+?轮|战略投资|战略融资|增资|募资|定增|基金.{0,8}(?:设立|成立|启动)|"
    r"(?:launch(?:es|ed)?|start(?:s|ed)?|raise[sd]?|secure[sd]?)\b.{0,28}\b(?:fund|funding|investment|financing)|"
    r"\bUSD\s*\d+(?:\.\d+)?\s*[mb]\b.{0,20}\bfund\b", re.I)
POLICY_TITLE_STRONG_R = re.compile(
    r"(?:国务院|国家|政府|委员会|发改委|能源局|工信部|工业和信息化部|生态环境部|自然资源部|"
    r"[一二三四五六七八九十\d]+个?部门|[\u4e00-\u9fa5]{2,12}(?:省|市|州|区)(?:政府|人民政府|主管部门)?)"
    r"[^\n]{0,35}(?:发布|印发|出台|批复|施行|"
    r"征求意见|通知|办法|政策|方案|规划|指南|标准|补贴|许可|申报)|"
    r"(?:四部门|三部门|两部门|多部门)联合发布|《[^》]{2,60}(?:政策|办法|通知|方案|规划|意见|细则|标准|指南)》",
    re.I)
RD_PLAN_TITLE_STRONG_R = re.compile(
    r"科研项目|研发项目|研发计划|研究计划|创新研发计划|国家重点研发|专项课题|基金项目|"
    r"(?:课题|项目).{0,12}(?:立项|获批|结题|验收)", re.I)
PROJECT_TITLE_STRONG_R = re.compile(
    r"项目.{0,12}(?:落地|备案|核准|公示|开工|建设|吊装|并网|投运|建成)|"
    r"(?:建设|新建|扩建|改造)[^，。；\n]{0,18}项目|"
    r"(?:备案|核准|环评|用地|选址)(?:信息)?公示", re.I)
PAPER_EV_R = re.compile(r"\bDOI\b|doi:|课题组|发表在|刊载于|期刊上线|preprint|arXiv|引用本文|教授团队|研究团队在")
# ③守卫：题名含明确产业事件动词（推出/交付/建成/招标…）时，正文论文引用只是背景，不作证据
INDUS_TITLE_R = re.compile(r"推出|发布|公布|发表|交付|建成|投产|并网|开工|建设|下线|量产|发射|开航|招标|中标|评标|签约|成立|奠基|封顶|交割|收购")
# ---- 分型消歧补丁扩展（2026-09-11 五次修订·S1 组）--------------------------------------
# 题名顶刊书名号（#2 类"登顶《Nature》"稿正文只有"XX实验室"字样，PAPER_EV_R 抓不到，
# 题名载体证据补入 research_ev，防 T01 正文触发词证据化后误杀真论文报道）
TITLE_PAPER_R = re.compile(r"登顶《|《[^》]{0,18}(?:Nature|Science|Cell|Joule|PNAS|Angew)[^》]{0,18}》|Nature子刊|"
                           r"Nature Communications|Nature Energy|Nature Catalysis")
# 消歧⑦：周刊/合辑类汇总稿题名正则（聚合容器，内部单事件词面无分型意义；"学报/期刊"类研究刊不在内）
DIGEST_TITLE_R = re.compile(r"双周刊|周刊|周报|月报|半月刊|合辑|汇编|集锦|大事记|新闻汇总|资讯汇总|"
                            r"top\s*\d+|(?:AI|科研|顶刊|新闻|资讯)速递\s*\d{6,8}\s*$|"
                            r"(?:要闻|速递)[^|｜]{0,12}(?:；|\.\.\.|…)", re.I)
# 消歧⑧：题名会议/活动证据（与 TYPE_TRIG_EXT["T24"] 同源词面，另补"召开/举办"事件动词）
CONF_EXT_TITLE_R = re.compile(r"研讨会|评审会|交流会|座谈会|(?<!股东)大会|峰会|年会|博览会|展览会|论坛|发布会|召开|举办")
# 消歧⑨：期刊论文全文转载稿——题名《刊名》文章，或正文"引用本文…DOI"文献条目（转载全文特征，
# 报告发布稿无此结构）
JOURNAL_TITLE_R = re.compile(r"《[^》]{2,20}》[^，。；|｜\n]{0,4}(?:文章|论文)")
CITE_DOI_R = re.compile(r"引用本文[\s\S]{0,200}?(?:DOI|doi\s*[:：])")
# 后段出现的明确论文载体证据；与 PAPER_EV_R 的“研究团队在”等宽触发分开，允许扫描完整清洗正文。
PAPER_EXPLICIT_R = re.compile(r"论文(?:已|被|正式)?发表在|发表(?:于|在)《[^》]{2,40}》(?:杂志|期刊)?|"
                              r"刊载于《[^》]{2,40}》|doi\s*[:：]|doi\.org/", re.I)
# 媒体转载论文的常见中文载体句和结构化栏目。原正则漏掉“在某期刊上发表题为…的研究论文”，
# 导致论文被 T05 项目卡按“意向/传闻”打分。必须同时有期刊/论文载体，不能仅凭“研究团队”。
PAPER_CARRIER_EXT_R = re.compile(
    r"在[^。；\n]{0,100}(?:期刊|Nature|Science|Cell|Joule|Advanced\s+Materials|Angew)[^。；\n]{0,100}"
    r"发表[^。；\n]{0,80}(?:题为|论文)|"
    r"(?:研究背景|工作简介)[\s\S]{0,1600}(?:研究论文|论文链接|DOI|Figure\s*\d)", re.I)
# 媒体摘编常把论文载体放在文末“来源：期刊 + URL/DOI”中；这是强于泛化“研究显示”的证据。
SOURCE_PAPER_R = re.compile(
    r"(?:来源\s*[:：]?\s*)?(?:Nature(?:\s+(?:Climate Change|Energy|Communications|Sustainability))?|"
    r"Science(?:\s+Advances)?|Cell|Joule|Energy\s*&\s*Environmental\s*Science|Advanced Materials)"
    r"[^\n]{0,100}?(?:https?://|doi|10\.\d{4,9}/)", re.I)

# 政府/欧盟正式推出的跨主体交易、匹配或监管机制属于政策制度，不是企业“产品平台”。
OFFICIAL_PLATFORM_TITLE_R = re.compile(r"(?:欧盟|政府|国家|委员会|能源局)[^\n]{0,30}(?:平台|机制)", re.I)
OFFICIAL_PLATFORM_BODY_R = re.compile(
    r"(?:欧盟委员会|政府|主管部门|能源局)[^。；\n]{0,100}(?:正式)?(?:启动|推出|建立|上线)[^。；\n]{0,80}"
    r"(?:机制|交易平台|买卖平台|匹配平台|监管平台)", re.I)
RD_PLAN_OBJECT_R = re.compile(r"科研项目|研发项目|研究计划|专项计划|课题|立项|项目申报|项目获批|基金项目")
TECH_BOTTLENECK_R = re.compile(r"瓶颈|难题|挑战|失效|腐蚀|能耗|效率.{0,8}(?:低|下降)|稳定性|寿命|复杂性")
TECH_SOLUTION_R = re.compile(r"提出.{0,30}(?:办法|方法|策略|路线|材料|体系)|通过.{0,40}(?:实现|抑制|降低|提升)|"
                             r"从.{0,30}(?:结构|机理|机制).{0,30}(?:入手|解决)|自动.{0,20}(?:生成|形成)")

MATURE_PV_R = re.compile(r"topcon|(?<![a-z])perc(?![a-z])|钝化接触", re.I)
NEW_PV_R = re.compile(r"钙钛矿|叠层|perovskite|tandem", re.I)

# 域消歧守卫（2026-09-11 五次修订·S6 组）。
# LED 采用英文边界，避免变量/长单词子串误命中；太阳能题名证据优先，防误杀钙钛矿光伏。
LED_SIDE_R = re.compile(
    r"(?<![A-Za-z])(?:PeLED|OLED|QLED)(?![A-Za-z])|light[- ]emitting(?:\s+diodes?)?|"
    r"发光二极管|电致发光|外量子效率|electroluminescen", re.I)
BARE_LED_R = re.compile(r"(?<![A-Za-z])LEDs?(?![A-Za-z])", re.I)
OPTO_CONTEXT_R = re.compile(r"钙钛矿|perovskite|发光|显示|光电|二极管|diode|emitting|蓝光|红光|绿光", re.I)
SOLAR_SIDE_R = re.compile(r"(?<![A-Za-z])(?:solar|photovoltaic)(?![A-Za-z])|光伏|太阳能|太阳电池", re.I)

# 载体域→最终产物/技术难点主体域。先只固化有反馈证据的“风/光供能→制氢”关系，
# 表结构保留扩展位；其它复合系统需回测后再加入，避免把风储/源网荷储一律翻域。
SUBJECT_PRIORITY = [
    {
        "carriers": {"D01", "D06"},
        "target": "D05",
        "carrier_r": re.compile(r"风光|海上风电|风电|光伏|太阳能|offshore wind|wind power", re.I),
        "subject_r": re.compile(r"制氢|绿氢|电解(?:水|槽)|hydrogen|electroly[sz]", re.I),
        "action_r": re.compile(
            r"(?:风光|海上风电|风电|光伏|太阳能).{0,20}(?:制氢|绿氢|电解(?:水|槽))|"
            r"(?:hydrogen|electroly[sz]).{0,20}(?:wind|solar)|(?:wind|solar).{0,20}(?:hydrogen|electroly[sz])",
            re.I),
        "label": "供能源（风/光）→制氢主体",
    },
]


def _subject_priority(item, formula_dom, ds, parts_by):
    """返回应优先的主体域与可审计理由；未命中返回 (None, "")。"""
    if formula_dom is None:
        return None, ""
    title = item["title"]
    scope = title + "\n" + item["body"][:600]
    for rule in SUBJECT_PRIORITY:
        target = rule["target"]
        if formula_dom["no"] not in rule["carriers"] or ds.get(target, 0) < 40:
            continue
        direct_title = bool(rule["action_r"].search(title))
        cooccur = bool(rule["carrier_r"].search(scope) and rule["subject_r"].search(scope)
                       and rule["action_r"].search(scope))
        if not (direct_title or cooccur):
            continue
        tp = parts_by[target]
        fp = parts_by[formula_dom["no"]]
        target_core_n = tp.get("core_title_n", 0) + tp.get("core_body_n", 0)
        carrier_core_n = fp.get("core_title_n", 0) + fp.get("core_body_n", 0)
        # 题名中明确“载体制主体”的动宾可直接裁决；仅正文共现则要求主体核心证据不弱于载体。
        if direct_title or target_core_n >= carrier_core_n:
            why = (f"主体优先:{rule['label']}（{'题名动宾' if direct_title else '前600字共现'}；"
                   f"{target}核心证据{target_core_n} vs {formula_dom['no']}核心证据{carrier_core_n}）")
            return DOM_BY_NO[target], why
    return None, ""


def _valid_secondary(parts):
    """次高域须有题名词面或正文至少两个核心词证据；主体清单/指标不能单独撑起次域。"""
    return bool(parts.get("title", 0) > 0 or parts.get("core_body_n", 0) >= 2)


def _led_evidence(text):
    """LED 光电证据计数；裸 LED 必须与光电上下文同现，避免把算法变量“LED”当器件。"""
    strong = len(LED_SIDE_R.findall(text))
    bare = len(BARE_LED_R.findall(text)) if OPTO_CONTEXT_R.search(text) else 0
    return strong + bare
FIRST_R = re.compile(r"世界纪录|纪录|刷新|突破|首个|首台|首套|首次|首单|首家|首条|首创|全球最|全国最|最大|最高|独创")

# ---------------- 评分卡机器层（02 簿 family_cards，简化口径见方法说明⑥） ----------------
CARDS = {c["card_id"]: c for c in D["family_cards"]}
# 选卡：TYPES.card 字符串取主卡（首个 card_*）；T15 card_resource 未建卡、T25 无卡 → None 转人工
CARD_OF_TYPE = {}
for _t in TYPES:
    _m = re.match(r"(card_[a-z]+)", str(_t.get("card") or ""))
    CARD_OF_TYPE[_t["id"]] = _m.group(1) if (_m and _m.group(1) in CARDS) else None

# TRL 初判：trl_framework.weights 检测词（簿面）＋ 中英文阶段词扩展；从 TRL9 往下扫，首个命中即档；未命中=None(权重 1.0)
TRL_W = {w["trl"]: w["weight"] for w in D["trl_framework"]["weights"]}
# TRL8"量产"负断言（2026-09-11 五次修订·S2 组）：中文"比功率（单位重**量产**生的功率）"跨词
#   误命中"量产"致论文转述稿被压 TRL8×0.9（#2a/#2b 根因之一）；(?<!重)量产 排除"重量产生"类。
_TRL_EXT = {9: r"投运|商运|commercial operation", 8: r"(?<!重)量产|并网|mass produc|commission(?:ed)?",
            7: r"prototype|路试", 6: r"中试|示范|实证|pilot", 5: r"",
            4: r"bench|台架|lab[- ]scale|scale[- ]up", 3: r"laborator",
            2: r"proof[- ]of[- ]concept|\bPOC\b", 1: r"mechanism|first[- ]principles|\bDFT\b|ab initio|propose"}
TRL_RX = []
for _w in sorted(D["trl_framework"]["weights"], key=lambda x: -x["trl"]):
    _p = [re.escape(p) for p in _w["detect"].split("|") if p]
    _p += [e for e in _TRL_EXT.get(_w["trl"], "").split("|") if e]
    TRL_RX.append((_w["trl"], re.compile("|".join(_p), re.I)))

# 阶段阶梯（02 簿 stage_ladder 同表）：装车/示范运行30 · 交付/客户验证26 · 量产/定型22 ·
#   中试/示范16 · 样品/样机10 · 仅宣布6 · 未说明4（"未说明≠0 记 4 并触发 Gate"由各卡 gate 实现）
TIER_RX = [(30, re.compile(r"装车|路试|道路测试|示范运行|(?<!支持)(?<!可)并网|投运|商运|商业运行", re.I)),  # S3 组补"道路测试"；"支持/可并网"仅为产品能力
           (26, re.compile(r"交付|定点|客户验证|第三方验收|验收|小批量|进入.{0,10}?市场", re.I)),  # S3 组补市场进入
           (22, re.compile(r"量产|投产|定型|批产|下线|mass produc", re.I)),
           (16, re.compile(r"中试|验证线|示范|实证|pilot", re.I)),
           (10, re.compile(r"样品|样机|小试|台架|prototype", re.I)),
           (6, re.compile(r"宣布|发布|推出|launch", re.I))]


def stage_tier(txt):
    for sc, rx in TIER_RX:
        if rx.search(txt):
            return sc
    return 4


# 维度初判共用词面信号（全部为简化近似：一线/二线主体、异常度、阶段匹配等语义不可判，以词表代之）
TOPJOURNAL_R = re.compile(r"Nature|Science|Joule|Cell|Advanced Materials|Angew|PNAS|ACS Nano|"
                          r"Energy Environ|Nature Energy|Nature Catalysis|JACS|Adv\.? Energy", re.I)

# ---------------- 文献评分+媒体转述通道（2026-09-11 五次修订·S2 组） ----------------
# 期刊档位表（任务书 A.2 机器层近似；档位分值全部 TODO(回测)，端点 20/12 沿用原两档制上限/普通档）：
#   顶档=Nature/Science/Cell 及子刊 20 ｜ 高档=Joule/EES/AM/Angew/JACS/PNAS 系 16
#   普通档=有 DOI 普通 SCI 12 ｜ 低档=预印本 6 ｜ 载体未识别(无 DOI) 6
# 高档名单=原 TOPJOURNAL_R 20 分名单中剔除 Nature/Science/Cell 系后的成员（ACS Nano/Adv Energy
#   维持高档不降普通档，避免一次改动降两档），子刊（Nature Energy/Catalysis/Communications）
#   经"Nature"前缀归顶档——清单显式、可解释，回写工作簿建议见 report。
JOURNAL_HIGH_R = re.compile(r"Joule|Energy Environ|Advanced Materials|Adv\.?\s*Mater\.?|Angew|PNAS|ACS Nano|JACS|"
                            r"Adv\.? Energy", re.I)
JOURNAL_TOP_R = re.compile(r"Nature|(?<![A-Za-z])Science(?![a-z])|(?<![A-Za-z])Cell(?![a-z])", re.I)
PREPRINT_R = re.compile(r"arxiv|biorxiv|chemrxiv|preprint|ssrn|researchsquare|preprints", re.I)
# 综述/观点识别（任务书 A.2）：题名命中 → 走期刊档位通道，不采瓶颈参数
REVIEW_R = re.compile(r"\breview\b|\breviews\b|\bsurvey\b|perspective|outlook|roadmap|"
                      r"综述|展望|路线图|进展与挑战", re.I)
# 文献英文"首发/纪录"词（FIRST_R 仅中文；英文文献题名/摘要 record 类词 → 突破档，任务书 A.1 强化）
FIRST_EN_R = re.compile(r"record[- ]breaking|world record|new record|record efficiency|"
                        r"record[- ]high|unprecedented", re.I)
# 媒体转述论文识别（任务书 B）：非文献源 + 题名非原创产业事件（INDUS_TITLE_R 守卫）+
#   （题名顶刊词 或 正文含 DOI/期刊/发表证据）；证据扫描全文（正文截 2500 已在上限）
RELAY_VENUE_R = re.compile(r"\bDOI\b|doi:|doi\.org|10\.\d{4,9}/|发表在|发表于|刊载于|刊于|见刊|"
                           r"杂志上|期刊上|论文发表|preprint|arXiv", re.I)
# 媒体转述指标档（任务书 B，#13 类）：纪录/首发词 + 通用单位数值 + 量化对比声明 → 自报超基线 20
RELAY_GAIN_R = re.compile(r"翻了?[一二两三四五六七八九十百\d]+\s*倍|提升[了至到]?\s*[一二两三四五六七八九十百\d]+\s*倍"
                          r"|的\s*[一二两三四五六七八九十百\d]+\s*倍以上")
# 权威媒体清单（任务书 C.4，显式可解释；加分常数 TODO(回测)）：新华社/科技日报/央视/人民日报=高加值
AUTH_MEDIA_R = re.compile(r"新华社|新华网|科技日报|央视|中央电视台|人民日报")
MEDIA_BONUS = {"authoritative": 5, "normal": 2}   # 每条媒体报道加分数 TODO(回测)
MEDIA_BONUS_CAP = 8                               # 单文献条目累计加分封顶 TODO(回测)
# 跨源合并工具（任务书 C）：DOI 提取/规范化、英文题名词集 Dice（复数容错 s/ies）
DOI_RX = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>)），。；、]+", re.I)
QUOTE_EN_R = re.compile(r"《([A-Za-z][^》]{10,200})》")


def _norm_doi(s):
    s = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", (s or "").strip(), flags=re.I)
    return re.sub(r"[^0-9a-z]", "", s.lower())


def _doi_values(s):
    vals = {_norm_doi(x) for x in DOI_RX.findall(s or "")}
    return {x for x in vals if x}


def _en_words(s):
    """英文题名词集规范化：小写、去非字母数字、复数容错（ies→y / 去尾 s，排除 ss/us/is）。"""
    out = []
    for w in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split():
        if len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            w = w[:-1]
        out.append(w)
    return out


def _word_dice(a, b):
    A, B = set(a), set(b)
    return 2 * len(A & B) / (len(A) + len(B)) if A and B else 0.0


def _alnum(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _journal_tier(item):
    """文献源期刊档位（meta=RSS 源名 + url 判档）。返回 (档名, 分值)——分值 TODO(回测)。"""
    m = " ".join((item.get("meta") or "", item.get("url") or "", item.get("title") or ""))
    if PREPRINT_R.search(m):
        return "预印本（低档）", 6
    if JOURNAL_HIGH_R.search(m):  # 高档先判：EES 含"Science"字样，若先判顶档会误升
        return "高档期刊（Joule/EES/AM/Angew/JACS/PNAS 系）", 16
    if JOURNAL_TOP_R.search(m):
        return "顶档期刊（Nature/Science/Cell 及子刊）", 20
    if (item.get("doi") or "").strip():
        return "普通 SCI（有 DOI）", 12
    return "载体未识别（无 DOI）", 6


def _is_media_relay(item):
    """非文献源的论文媒体转述；产业事件标题仍由原卡处理，防背景引文误升档。"""
    if item.get("src") == "literature" or INDUS_TITLE_R.search(item.get("title") or ""):
        return False
    title = item.get("title") or ""
    body = item.get("body") or ""
    return bool(JOURNAL_TOP_R.search(title) or JOURNAL_HIGH_R.search(title)
                or RELAY_VENUE_R.search(body))


def _relay_journal_tier(item):
    """媒体转述稿中可见的期刊证据分档；识别不到刊名但有 DOI/发表证据时按普通档。"""
    txt = " ".join((item.get("title") or "", item.get("body") or ""))
    if JOURNAL_HIGH_R.search(txt):
        return "高档期刊媒体转述", 16
    if JOURNAL_TOP_R.search(txt):
        return "顶档期刊媒体转述", 20
    return "普通期刊/DOI 媒体转述", 12
THIRD_R = re.compile(r"第三方|认证|检测机构|型式试验|国标|实测|验收|质检|标定|ASTM|IEC")
# 验证卡将国际标准符合性计入第三方条件，并识别车企—技术方联合开发场景。
JOINT_R = re.compile(r"联合验证|业主|客户共同|双方验证|配套验证|联合开发|共同开发|协同开发")
MECH_R = re.compile(r"新机理|机理|机制|新路线|新策略|新体系|新设计|首次提出|novel|mechanism|insight|新概念|解耦|重构")
INCR_R = re.compile(r"新工艺|新技术|改进|优化|升级|新一代|增强|提升|新方法|新方案")
BROKE_R = re.compile(r"破产|接管|重组|退市|清算|退出|质押违约|资金链断裂")
SWING_R = re.compile(r"扭亏|预增|预减|超预期|盈亏反转|大幅增长|大幅下滑|亏损扩大|暴涨|暴跌|翻倍|腰斩")
ROUTINE_R = re.compile(r"业绩|营收|净利|季报|年报|财报|营收增长")
LEAD_R = re.compile(r"龙头|头部|领军|全球领先|世界第一|市占率|市占|出货量第|独角兽")
FIRM_R = re.compile(r"公司|集团|股份|研究院|研究所|大学|院|有限|实验室|Lab|Inc|Corp|Ltd")
NATION_R = re.compile(r"国家|国资|央企|国务院|部委|产业基金|主权基金|政府|国投|国电投|中石化|中石油|中海油|中核|中广核|国家电网|南方电网")
FIN_R = re.compile(r"资本|基金|投资|机构|创投|风投|PE|IB")
ROUND_R = re.compile(r"天使|种子|[A-E]\+?轮|Pre-?IPO|IPO|战略投资|战略融资|增资|募资|定增")
USE_R = re.compile(r"中试|产线|产能|扩产|基地|材料|研发|工厂|制造|设备")
AMT_BIG_R = re.compile(r"\d+(?:\.\d+)?\s*亿|[$€£]\s*\d+(?:\.\d+)?\s*[MB]|\d+(?:\.\d+)?\s*万(?:美元|欧元|英镑)", re.I)
AMT_SMALL_R = re.compile(r"\d+(?:\.\d+)?\s*万(?:元|人民币)")
PCT_NEAR_R = re.compile(r"(?:涨|跌|上升|下降|增长|下滑|上涨|回落|下跌|降幅|增幅|环比|同比)[^。；;,\n]{0,14}?(\d{1,3}(?:\.\d+)?)\s*%")
BASE_R = re.compile(r"同比|环比|基期|较上年|上年同期|相比|versus|较去")
RUMOR_R = re.compile(r"传闻|据传|消息称|业内消息|知情人士")
SCALE_ABS_R = re.compile(r"最大|全球最|全国最|首个|首条|首个百|世界纪录|纪录")
YIELD_R = re.compile(r"良率|利用率|可用系数|可靠性|运行率|转换效率|energy yield")
DUR_R = re.compile(r"1000\s*[hH小时]|千小时|1000\s*次|万公里|连续运行|跨季节|累计|full[- ]year")
DUR2_R = re.compile(r"连续|持续|single[- ]point|当月|单月|季度")
YARD_R = re.compile(r"开工|封顶|吊装|浇筑|主体工程")
EPC_R = re.compile(r"中标|EPC|总承包|正式合同|审批|核准|获批|融资完成|资金已落实|定标|公示")
INTENT_R = re.compile(r"意向|备忘录|MOU|框架协议|拟|计划|预计|传闻")
STRONG_EV_R = re.compile(r"投产|满产|并网|投运|建成|全容量|商运|交付")
# 评分卡修订（2026-09-11 五次修订·S3 组）：强事件词表补"交付"（原 card_project 35 档注记
#   "投产/并网/交付运行"但词面缺"交付"，交付类项目稿全落到 12/5 档）；新增验证里程碑与
#   投资落定事件类（阶段跃迁 22/18 档、工程确定性 12/10 档，档值 TODO(回测)）——
#   试飞/路试/示范运行/市场进入=里程碑验证事件，投资约+金额/持股=项目资金落定。
MILESTONE_EV_R = re.compile(r"试飞|首飞|载人|道路测试|路试|示范运行|完成.{0,32}?(?:试验|验证)|进入.{0,10}?市场")
INVEST_EV_R = re.compile(r"投资[约达]?\s*\d|增资|注资|各持股|持股\s*\d|成立合资|合资公司|募投")
# 评分卡修订（2026-09-11 五次修订·S3 组）：建成中交/机械竣工只是施工转联调，非投产投运。
MECH_COMPLETE_R = re.compile(r"建成中交|机械竣工|中间交接|转入(?:联动)?调试|投料试车")
OPERATION_EV_R = re.compile(r"投产|满产|并网|投运|全容量|商运|商业运行|正式运营")
NEG_EV_R = re.compile(r"停产|事故|骤降|爆炸|火灾|停产检修|关停")
RAMP_R = re.compile(r"爬坡|扩产|技改|升级改造|改造|增产")
ROUT_RUN_R = re.compile(r"运行|产出|通报|产量|发电量|出货")
MANDATE_R = re.compile(r"强制|禁令|配额|准入|强制性|淘汰|限制|禁止|必须")
SUBSID_R = re.compile(r"补贴|税收|电价|奖励|免征|退税|减免|贴息")
FIRST_DOC_R = re.compile(r"首个|首次|第一份|填补|首部|第一个")
TOP_TALENT_R = re.compile(r"院士|首席科学家|创始人|CEO|CTO|带头人|核心团队|总师|首席技术官")
MID_TALENT_R = re.compile(r"高管|副总裁|总监|总经理|董事长|总裁|教授|博士")
TEAM_SCALE_R = re.compile(r"\d+\s*人|成建制|团队整体|研发中心|整建制")
CHoke_R = re.compile(r"独家|垄断|唯一|卡脖子|不可替代|独家供应")
SUP_MAJOR_R = re.compile(r"主要供应商|核心供应商|主力供应|重要供应商|供应商")
CUT_R = re.compile(r"断供|禁运|出口管制|停供|管制|制裁")
SUBST_R = re.compile(r"国产替代|第二供应|第二源|自主可控|本土化|自主化")
LTA_R = re.compile(r"长协|框架|锁定|长约")
REPL_OK_R = re.compile(r"替代.{0,12}(验证|通过|量产|认证)|已验证|验证通过")
REPL_CLAIM_R = re.compile(r"可替代|替代方案|备选")
SCOPE_ALL_R = re.compile(r"全球|全国|全域|全行业|整个行业|多国|国际市场|国际")
STRUCT_R = re.compile(r"格局|结构|趋势|长期|供需|产能过剩|结构性")
ALERT_R = re.compile(r"断供|管制|制裁|安全|壁垒|风险|预警")
VALID_SCALE_R = re.compile(r"真实工况|示范|全尺寸|整车|电站|系统级|实地|现场|试飞|飞行|载人")
PILOT_R = re.compile(r"中试|缩放|pilot|试点")  # S3 组补"试点"（试点装置≈中试级，仅 card_validation）
BENCH_R = re.compile(r"台架|实验室|小样|lab[- ]scale|bench")
PASS_R = re.compile(r"通过|合格|达标|满足要求|成功验证")
SPEC_R = re.compile(r"[A-Z]{2,4}[- ]?\d{2,4}[A-Z]?型?|新一代|新型号|系列")
CALIB_R = re.compile(r"测试条件|口径|IEC|GB/T|标准条件|STC|25°C|AM1\.5|同口径|可比")

# 商务类前置证据与分级（S4）：无技术突破、无头部重大合并的商务动态不得进高档。
TECH_BREAK_FACT_R = re.compile(r"刷新[^。；\n]{0,14}纪录|创[^。；\n]{0,10}纪录|世界纪录|亚洲纪录|全国纪录|"
                               r"首个|首台|首套|首条|首次|首创|全球首")
MERGER_MAJOR_R = re.compile(r"(?:头部|巨头|龙头|行业|产业|重大).{0,8}(?:合并|并购|收购|重组|整合)"
                            r"|(?:合并|并购|重组).{0,8}(?:获批|完成|落地|敲定)")
EQ_ROUND_R = re.compile(r"天使|种子|[A-E]\+?轮|Pre-?IPO")
CAP_OP_R = re.compile(r"战略投资|战略融资|增资|募资|定增|启动IPO|IPO窗口")
BID_SVC_R = re.compile(r"监理|咨询|招标代理|造价|审计|技术服务|勘察")
EPC_LIKE_R = re.compile(r"EPC|总承包|设计[-－—~·]*施工|施工[-－—~·]*运营|交钥匙|设计采购施工")
STAT_PERIOD_R = re.compile(r"一季度|二季度|三季度|四季度|月度|单月|季度|上半年|当月|装机数据|装机统计")
INFLECT_STRONG_R = re.compile(r"首次转正|首次超越|首次反超|反超|历史性|拐点|重塑|逆转|超越火电|超越煤电")

# 政策申报、单笔融资与稀缺路线市场进入的证据化规则。
POLICY_PROJECT_CALL_R = re.compile(
    r"(?:再次)?组织.{0,8}申报|申报.{0,12}(?:启动|通知|项目清单)|"
    r"(?:项目|建设)清单.{0,10}(?:申报|报送)|启动.{0,8}(?:项目)?申报")
OFFICIAL_POLICY_DOC_R = re.compile(
    r"(?:发展改革委|发改委|能源局|工业和信息化(?:部|厅|局)|工信(?:部|厅|局)|"
    r"人民政府|生态环境(?:部|厅|局)|自然资源(?:部|厅|局)|主管部门)"
    r"[^。；\n]{0,45}(?:发布|印发|出台|下发)[^。；\n]{0,12}《[^》]{2,100}"
    r"(?:通知|办法|方案|意见|规划|细则|清单)[^》]*》")
POLICY_ROUTE_REQ_R = re.compile(
    r"构网型|长时储能|压缩空气|全钒液流|液流电池|钠离子|飞轮|重力储能|"
    r"氢储能|热储能|技术路线.{0,20}(?:优先|鼓励|要求|采用)")
FIN_KEY_METRIC_R = re.compile(
    r"\d+(?:\.\d+)?\s*(?:Wh/kg|Wh/L|mAh/g|mS/cm|S/cm|次循环|循环|C倍率|MPa)"
    r"|(?:效率|保持率|良率|能量效率|衰减率)[^。；\n]{0,12}\d+(?:\.\d+)?\s*%"
    r"|\d+(?:\.\d+)?\s*%[^。；\n]{0,10}(?:效率|保持率|良率|衰减)", re.I)
FIN_TECH_VERIFY_R = re.compile(
    r"第三方|实测|客户验证|量产验证|认证|检测报告|通过.{0,12}(?:验证|测试)|"
    r"刷新.{0,12}纪录|世界纪录|首创|首次实现|独家专利")
FIN_TREND_AGG_R = re.compile(
    r"融资趋势|投融资趋势|融资统计|投融资统计|融资盘点|投融资盘点|"
    r"多家.{0,12}融资|\d+家.{0,12}融资|融资事件.{0,12}(?:共|合计|达到|增长)")
SCARCE_STORAGE_ROUTE_R = re.compile(
    r"固态(?:锂)?电池|半固态(?:锂)?电池|全钒液流|液流电池|钠离子(?:电池)?|"
    r"压缩空气储能|二氧化碳(?:电池|储能)|飞轮储能|重力储能|氢储能|热储能")
EMERGING_MARKET_R = re.compile(
    r"非洲|尼日利亚|肯尼亚|南非|埃及|埃塞俄比亚|加纳|坦桑尼亚|乌干达|"
    r"拉美|东南亚|南亚|中东|新兴市场")
MARKET_ENTRY_FACT_R = re.compile(
    r"在[^。；\n]{0,35}(?:举行|举办).{0,12}产品发布|"
    r"(?:产品|品牌)[^。；\n]{0,20}(?:进入|登陆|进军|落地)[^。；\n]{0,20}(?:市场|国家|地区)|"
    r"在[^。；\n]{0,25}(?:上市|销售|交付|落地)|建立(?:本地|当地)?(?:工厂|产线|销售网络)")

# 稀缺长时储能项目只在“量化时长/规模 + 具名业主合作/选址”同时出现时升到中档；
# 计划本身仍不能按建成或投运计分。
SCARCE_LDES_PROJECT_R = re.compile(r"二氧化碳(?:电池|储能)|压缩空气储能|液态空气储能|液流电池|重力储能")
LDES_DURATION_R = re.compile(r"(?:\d+(?:\.\d+)?\s*(?:小时|h)\b|长时储能)", re.I)
PROJECT_COMMIT_R = re.compile(r"(?:公司|公用事业|能源局|政府|业主)[^。；\n]{0,80}(?:共建|合作|签署|选址|项目)|"
                              r"(?:共建|合作建设|选址于|位于)[^。；\n]{0,80}(?:项目|电站|系统)")

# 政策、报告与汇总类规则（S5）。
STD_ACCESS_R = re.compile(r"分级分类|分级标准|能效限定|能效等级|能效标杆|市场准入|准入门槛|准入条件|"
                          r"淘汰(?:落后|低效|老旧)|重塑市场")
POLICY_DEPLOY_R = re.compile(r"设备更新|更新升级|改造升级|节能降碳改造|专项行动|三年行动|行动方案|行动通知|"
                             r"应改尽改|应提尽提|加快.{0,12}(?:改造|更新|升级|推广|开展)")
POLICY_MARKET_MECH_R = re.compile(r"正式(?:启动|推出|建立|上线).{0,30}(?:交易|买卖|匹配|监管)?(?:平台|机制)|"
                                  r"(?:交易|买卖|匹配|监管)(?:平台|机制).{0,20}(?:启动|推出|建立|上线)")
POLICY_SCOPE_R = re.compile(r"全国性|全国范围|在全国|全国统一|欧盟(?:范围|层面|各国|成员国)?|欧洲范围|跨国|"
                            r"全域|全行业|多部门|\d+部门|"
                            r"[一二三四五六七八九十]部门|等部门|会同有关部门|重点行业|行业标准|国家标准|"
                            r"强制性国标|多国协同|国际标准")
BLANK_NEW_R = re.compile(r"原先没有|原本没有|首次出台|新出台|填补空白|从无到有|全新的(?:规则|标准|制度|体系)")
RULE_WORD_R = re.compile(r"标准|规范|规则|制度|政策|新政|办法|通知|方案|条例|法规|目录|清单")
REPORT_CARRIER_R = re.compile(r"报告|白皮书|蓝皮书|绿皮书|皮书|展望|年报|榜单|排名|指数")
JOURNAL_GUARD_R = re.compile(r"期刊|学报|杂志|文章|论文|Journal|综述|第\s*\d+\s*期")
CALL_FOR_R = re.compile(r"征集中|征文|征稿|报告专家|报名|参会|日程|交通指南|论坛|大会|峰会|研讨会|年会|博览会|展览会|会议")
AUTH_ORG_A_R = re.compile(r"IEA|IRENA|国际能源署|国际可再生能源署|BNEF|BloombergNEF|彭博新能源财经|彭博|DNV|"
                          r"挪威船级社|船级社|标普全球|S&P|Wood\s?Mackenzie|伍德麦肯兹|麦肯锡|EIA|"
                          r"美国能源信息署|Rystad|Lazard|BCG|罗兰贝格|IHS", re.I)
AUTH_ORG_B_R = re.compile(r"中国科学院|中科院|文献情报|战略情报|工程院|国务院发展研究中心|国研中心|"
                          r"国网能源研究院|水规总院|水电总院|电力规划设计总院|赛迪|智库|科学技术信息研究所|情报研究所", re.I)
REPORT_SERIES_R = re.compile(r"第\s*([5-9]|[1-9]\d+)\s*(?:版|期|年)|连续(?:发布|跟踪).{0,8}([5-9]|[1-9]\d+)\s*年")
DIGEST_COLUMN_R = re.compile(r"双周刊|半月刊|周刊|周报|月报|汇编|汇总|合辑|速递|盘点|大事记|排行|榜单|TOP\s*\d+|一周")

# 已验收并交付/发运的集成系统不等于“长期运行”，但比单点瞬时多一层跨环节持续性证据。
DELIVERED_ACCEPTED_R = re.compile(r"(?:完成|通过).{0,24}(?:调试|验收).{0,24}(?:交付|发运)|"
                                  r"(?:交付|发运).{0,30}(?:项目现场|客户)")
# 产品相对既有方案的量化成本/能耗/效率对比，应进入性能中上档；须同时出现比较词和至少两个数值。
COMPARATIVE_PERF_R = re.compile(r"(?:降至|降低至|低于|高于|提升至|提高至|由.{0,30}(?:升至|降至))", re.I)

# 会议、观点与深度分析的软信息通道（S7）：避免拿性能参数卡硬评软信息。
AUTH_INST_R = re.compile(
    r"彭博新能源财经|BloombergNEF|\bBNEF\b|标普|S&P\s?Global|普氏|Platts|\bIEA\b|国际能源署|"
    r"\bIRENA\b|国际可再生能源署|\bDNV\b|伍德麦肯兹|Wood\s?-?\s?Mac(?:kenzie)?|WoodMac|睿咨得|"
    r"Rystad|IHS\s?Markit|麦肯锡|McKinsey|Lazard|Ember|Agora|中科院|中国科学院|"
    r"中国工程院|文献情报中心|战略情报|双碳情报|机械工业信息研究院|机工文献|水规总院|"
    r"水电水利规划设计总院|中电联|\bCNESA\b", re.I)
THINK_TANK_R = re.compile(r"研究院|研究所|情报中心|智库|学会|协会|大学|学院|工程院")
TOP_SPEAKER_R = re.compile(r"院士|首席科学家|创始人|首席执行官|\bCEO\b|\bCTO\b|总师|董事长|总裁|教授")
BUZZ_R = re.compile(r"热销|刷屏|爆火|出圈|疯抢|断货|翻车|风口|争议|噱头|割韭菜|智商税|真相|揭秘|火得|火爆")
POPSCI_R = re.compile(r"科普|深度|解读|一文读懂|一文看懂|剖析|指南|扫盲|白话")
DEPTH_R = re.compile(r"现状|趋势|格局|展望|预测|研判|剖析|复盘|逻辑|路线图|供需|市场份额|CAGR|解读|"
                     r"里程碑|结构性|商业模式|规模化|降本|应用场景|关键挑战")
CALIB2_R = re.compile(r"同比|环比|基期|较上年|较\d{4}年|预计|预测|到20\d\d年|未来\d+年")
STRATEGIC_TOPIC_R = re.compile(
    r"(?:数据中心|算力中心|人工智能).{0,60}(?:用电|电力需求|能源|燃气发电|CCUS|碳捕集)|"
    r"(?:水泥|钢铁|化工|航运|航空).{0,60}(?:脱碳|减排|降碳|碳锁定|AI|人工智能)", re.I)
INDUSTRY_AI_R = re.compile(r"(?:水泥|钢铁|化工|航运|航空).{0,20}(?:AI|人工智能)|"
                           r"(?:AI|人工智能).{0,20}(?:水泥|钢铁|化工|航运|航空)", re.I)
DISTINCT_VIEW_R = re.compile(r"复兴|关键答案|新拐点|碳锁定|结构性缺口|重新审视|突破口|路径锁定|竞争力")
OFFICIAL_VALIDATION_R = re.compile(r"官方(?:信息|公告|披露)|公司公告|官网|官方新闻稿|正式公告")
MULTI_COND_STABLE_R = re.compile(
    r"(?:启动|启停).{0,50}(?:停机|负载|调度).{0,80}(?:稳定|保持)|"
    r"(?:负载变化|变负荷|动态响应|多工况).{0,50}(?:稳定|通过|正常)")
MODEL_INSIGHT_R = re.compile(r"模型|测算|情景分析|综合评估|碳锁定|路径锁定|碳预算|投资决策")
CONF_EDITION_R = re.compile(r"第([一二三四五六七八九十百\d]+)届")
CONF_INTL_R = re.compile(r"国际(?:大会|峰会|论坛|会议|博览会|展会)|全球(?:大会|峰会|论坛|会议|博览会)|国家级")
CONF_HOST_R = re.compile(
    r"(?:主办|联合主办|联办|承办|指导单位)[^。]{0,80}?"
    r"(?:科学院|工程院|学会|协会|联合会|促进会|能源局|工业和信息化部|发改委|中能建|国家电网|"
    r"南方电网|中石化|中石油|中海油|中核|中广核|国家能源集团|国家电投|华能|大唐|华电|三峡|"
    r"设计院|规划设计总院)")
CONF_SCALE_R = re.compile(r"历史最大|最大规模|展商\s*\d+\s*\+|参展商?\s*\d+\s*\+|专业观众|龙头企业参展|头部企业|我国唯一|全国唯一")
CONF_BOOK_R = re.compile(r"《[^》]{2,30}?(?:白皮书|蓝皮书|绿皮书|皮书|发展报告|研究报告|产业报告|年度报告|榜单|指数)》")
CONF_PUBACT_R = re.compile(r"(?:发布|推出|首发|首秀|首推|颁[布发]|展出|签约).{0,16}?"
                           r"(?:白皮书|蓝皮书|皮书|报告|技术|产品|装备|系统|平台|解决方案|成果|标准|战略|新品)")
CONF_SHOW_R = re.compile(r"(?:展示|展出|亮相|涵盖|覆盖).{0,20}?(?:技术|产品|装备|解决方案|新品)")
CONF_AGENDA_R = re.compile(r"议程|议题|演讲嘉宾|主论坛|分论坛|展位|展台|展区|参展|奖项|大奖|颁奖|参观考察|报名|参会")
CONF_REVIEW_R = re.compile(r"评审会|审查会|验收会|论证会|预可研|可研评审|评审意见|研讨会")
SOFTINFO_TIDS = ("T22", "T23", "T24")


def _cn2int(s):
    if s.isdigit():
        return int(s)
    d = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if "百" in s:
        return 100
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        return d.get(a, 1) * 10 + d.get(b, 0)
    return d.get(s, 0)


def _digest_multi_n(body):
    n = len(re.findall(r"\*{0,6}\s*(?:\d{1,2}|[一二三四五六七八九十])[、．.](?!\d)", body))
    n += len(re.findall(r"[①-⑳]", body))
    n += len(re.findall(r"点击(?:阅读|查看)(?:详情|全文)", body))
    n += 3 * len(re.findall(r"共\s*\d+\s*条", body))
    return n


def is_digest(item):
    """栏目词加多条目证据，或短栏目名；单篇深度盘点不拦截。"""
    title = item["title"]
    if not DIGEST_COLUMN_R.search(title):
        return False
    if _digest_multi_n(item["body"]) >= 3 or len(re.sub(r"[\W_]+", "", title)) <= 10:
        return True
    return any(DIGEST_COLUMN_R.search(seg) and len(re.sub(r"[\W_]+", "", seg)) <= 10
               for seg in re.split(r"[|｜]", title))


def score_card(item, tid, dom, dparts, trl_override=None):
    """按 02 簿 family_cards 机器初判（简化口径）。
    返回 (raw, dims, trl, w, cap)：raw=Σ维度分(未乘 TRL/未封顶)、dims=[[维度,得分,满分,档说明]]、
    trl=TRL 初判(None=未判)、w=TRL 权重(A/B 组卡)、cap=Gate 封顶(None=无)。"""
    t, b = item["title"], item["body"]
    txt = t + "\n" + b[:1000]
    lit = item["src"] == "literature"
    relay = _is_media_relay(item) or bool(SOURCE_PAPER_R.search(item["body"]))
    review = bool(REVIEW_R.search(t))
    dom_unit = dparts["metric"] >= 15   # 数值+域单位（≈同口径可判档）
    gen_unit = dparts["metric"] > 0     # 数值+通用单位（口径不可比档）
    # S3 卡内量纲兜底：草案域尚无完整 units 时，工程/产品的中文量纲仍应参与评分，
    # 但性能量纲与工程规模量纲分开，避免把百分比或温度误作项目规模。
    gen_unit_card = gen_unit or bool(NUM_CARD_R.search(t) or NUM_CARD_R.search(b))
    gen_scale_card = bool(NUM_SCALE_R.search(t) or NUM_SCALE_R.search(b))
    draft_dom = dom["status"] == "draft"
    metric_eff = dom_unit or (draft_dom and gen_unit_card)
    scale_eff = dom_unit or (draft_dom and gen_scale_card)
    # 文献/媒体转述允许从摘要前段识别英文或中文纪录证据；普通产业稿仍只信题名，防宣传正文误升档。
    first_t = bool(FIRST_R.search(t)) or bool((lit or relay)
                   and (FIRST_EN_R.search(t + "\n" + b[:600]) or FIRST_R.search(b[:600])))
    tcore2 = dparts["title"] >= 40      # 题名域核心词 ≥2（≈命中 CORE 瓶颈）
    # 专属路线词虽不一定存在于旧 core_terms，也应视为至少 SECONDARY，而非“仅正文相关”。
    tcore1 = dparts["title"] >= 28 or dparts.get("route", 0) > 0
    actor = dparts["actor"] > 0
    n_unit = len(NUM_CARD_R.findall(txt))
    scarce_emerging_entry = bool(SCARCE_STORAGE_ROUTE_R.search(txt)
                                 and EMERGING_MARKET_R.search(txt)
                                 and MARKET_ENTRY_FACT_R.search(txt)
                                 and n_unit >= 2)
    trl = None
    for _trl, _rx in TRL_RX:
        if _rx.search(txt):
            trl = _trl
            break
    # 严格机制调用方可传入“路线前沿 TRL”。事件阶段只用于定位新闻所处阶段，
    # 不能替代评分机制 S3 所要求的路线成熟度。
    if trl_override is not None:
        trl = trl_override
    # 正文"建成/投运"证据的将来时抑制：『建成后/投运后/达产后…可实现』类展望句不算阶段事实
    # 评分卡修订（2026-09-11 五次修订·S3 组）：检索窗 600→1000 字（投产/交付事实常在导语后
    #   的项目概况段，600 字内漏检→阶段跃迁误落 12/5 档 TODO(回测)）；将来时抑制词补
    #   "计划/可能/有望"（"商业运营可能于2028年开始"类展望句不算投运事实）
    body6 = b[:1000]
    body_strong = bool(STRONG_EV_R.search(body6)) and \
        not re.search(r"建成.{0,4}后|投运后|并网后|达产后|投产后|预计|即将|拟|计划|可能|有望", body6)
    cid = CARD_OF_TYPE[tid]
    weighted = "是" in str(CARDS[cid].get("trl_weighted", ""))
    w = TRL_W[trl] if (trl and weighted) else 1.0
    na_perf = 12 if trl in (1, 2, 3) else (6 if trl in (4, 5, 6, 7, None) else 0)  # 无数值 NA（簿面）
    dims = []

    def dim(name, got, mx, note):
        dims.append([name, min(got, mx), mx, note])

    cap = None
    if cid == "card_product":
        tier = stage_tier(txt)
        if scarce_emerging_entry:
            tier = max(tier, 26)
        tier_note = {30: "装车/路试/道路测试/示范运行/并网", 26: "交付/客户验证/市场进入",
                     22: "量产/定型/批产", 16: "中试线/验证线",
                     10: "样品/样机", 6: "仅宣布", 4: "未说明"}[tier]
        if scarce_emerging_entry:
            tier_note = "稀缺储能路线×新兴市场实际发布/落地×≥2项量化规格 → 市场进入"
        dim("阶段阶梯", tier, 30, tier_note)
        if first_t and metric_eff:
            dim("性能×域阈值", 30, 30, "首发/纪录词+域单位数值≈突破档(幅度不可判；草案域以通用规模单位兜底)")
        elif COMPARATIVE_PERF_R.search(txt) and n_unit >= 2:
            dim("性能×域阈值", 22, 30, "至少两项数值+明确相对比较（成本/能耗/效率）≈量化改进档")
        elif metric_eff:
            dim("性能×域阈值", 15, 30, "数值+域单位≈达域基线(是否超基线不可判；草案域以通用规模单位兜底)")
        elif gen_unit_card and n_unit >= 3:
            dim("性能×域阈值", 15, 30, "≥3项量化规格披露≈可比中档 TODO(回测)")
        elif gen_unit_card:
            dim("性能×域阈值", 8, 30, "数值+通用单位≈口径/路线不可比（含中文工程单位）")
        else:
            dim("性能×域阈值", na_perf, 30, f"无数值 NA（TRL{trl or '未判'}）")
        spec_v = 15 if n_unit >= 3 else (8 if n_unit >= 1 else (3 if SPEC_R.search(txt) else 0))
        dim("规格/容量披露", spec_v, 15,
            {15: "容量+≥2项规格", 8: "部分数值披露", 3: "仅型号名", 0: "未说明"}[spec_v])
        lv = 15 if (actor and LEAD_R.search(txt)) else (10 if actor else (6 if FIRM_R.search(txt) else 6))
        dim("主体层级", lv, 15, {15: "域主体清单+一线词", 10: "域主体清单命中", 6: "初创/未知"}[lv])
        dim("指标完整性与口径", 10 if CALIB_R.search(txt) else (5 if (metric_eff or n_unit >= 3) else 0), 10,
            "口径词齐全/仅域单位/无口径")
        if not (dom_unit or gen_unit_card) and tier <= 6:
            cap = min(cap or 100, 40)  # Gate：无性能数值且无阶段证据 → 宣传性发布封顶 40
            # （S3 组：无数值判定改卡内口径，中文工程单位计入"有数值"）
        if trl in (8, 9) and not (dom_unit or gen_unit_card):
            cap = min(cap or 100, 60)  # Gate：TRL8-9 且无性能数值 → 封顶 60（同上卡内口径）
    elif cid == "card_tech" and tid == "T23" and len(b) >= 500 \
            and not STRATEGIC_TOPIC_R.search(t + "\n" + b[:1600]) \
            and TECH_BOTTLENECK_R.search(b[:1600]) and TECH_SOLUTION_R.search(b[:1600]):
        # 非论文载体的技术详述稿：评价“瓶颈→方案→机理/效果”的信息密度，不冒充论文突破。
        # 无论文/第三方证据时封顶中档，避免宣传型技术解读进入高档。
        w = 1.0
        route_v = 25 if tcore2 else (20 if tcore1 else 10)
        chain_v = 30 if len(b) >= 1000 else 22
        mech_v = 18 if (MECH_R.search(txt) or TECH_SOLUTION_R.search(b[:1600])) else 8
        source_v = 15 if re.search(r"大学|研究院|研究所|科学院|科学技术协会", item["meta"] + b[:1800]) else 8
        complete_v = 10 if len(b) >= 1000 else 5
        dim("技术详述通道", 0, 0, "非项目载体：瓶颈—方案—机理信息链；不等同论文或工程验证")
        dim("路线与领域相关性", route_v, 25, "专属路线/题名核心词证据")
        dim("瓶颈—方案链", chain_v, 30, "正文同时披露瓶颈与解决方案")
        dim("机理/效果解释", mech_v, 20, "机理或因果解决路径")
        dim("信源可核查性", source_v, 15, "科研机构/科协来源 15 · 一般来源 8")
        dim("正文完整度", complete_v, 10, "正文≥1000字 10 · ≥500字 5")
        if not relay and not THIRD_R.search(txt):
            cap = min(cap or 100, 79)
    elif cid == "card_tech" and tid in SOFTINFO_TIDS and not relay:
        # T24：会议影响力与实质发布双判据；T22/T23：分析质量与话题监测择高。
        # 软信息不适用技术成熟度，因此不乘 TRL 权重。
        w = 1.0
        src_all = t + "\n" + b[:2000]
        n_unit_sf = len(NUM_UNIT_R.findall(src_all))
        dom_sc3 = 20 if tcore2 else (12 if tcore1 else (6 if dparts["body"] > 0 else 3))
        if tid == "T24":
            m_ed = CONF_EDITION_R.search(t) or CONF_EDITION_R.search(src_all)
            n_ed = _cn2int(m_ed.group(1)) if m_ed else 0
            ed_sc = min(15, 6 + 2 * (n_ed - 3)) if n_ed >= 3 else 0
            intl = bool(CONF_INTL_R.search(src_all))
            host = bool(CONF_HOST_R.search(src_all))
            scale = bool(CONF_SCALE_R.search(src_all))
            infl = ed_sc + (10 if intl else (8 if host else 0)) + (5 if scale else 0)
            infl_hit = n_ed >= 3 or intl or host or scale
            infl_note = (f"届数:第{n_ed}届{'✓' if ed_sc else '✗'} + "
                         + ("国际/全球级会议词✓" if intl else ("权威机构主办/联办✓" if host else "主办权威:未检出✗"))
                         + f" + 规模阵容{'✓' if scale else ':未检出✗'}")
            book = CONF_BOOK_R.search(b)
            act = CONF_PUBACT_R.search(src_all)
            show = CONF_SHOW_R.search(src_all)
            if book:
                rel, rel_note = 30, f"书名号成果物✓ {book.group(0)[:24]}"
            elif act:
                rel, rel_note = 24, "发布/首秀/签约动词+技术产品对象✓"
            elif show:
                rel, rel_note = 15, "展示/亮相+技术产品对象✓（陈列级）"
            else:
                rel, rel_note = 0, "发布物:未检出✗"
            ag = len(set(CONF_AGENDA_R.findall(src_all)))
            ag_sc, ag_note = ((15, f"议程/嘉宾/展商阵容词{ag}类✓") if ag >= 3 else
                              ((8, f"议程类词{ag}类") if ag else (2, "议程信息未披露")))
            dim("软信息通道", 0, 0, "T24 会议双判据通道（影响力+实质发布），不乘 TRL 权重")
            dim("会议影响力", infl, 30, infl_note)
            dim("实质发布", rel, 30, rel_note)
            dim("域关联", dom_sc3, 20, "题名核心词≥2/1/仅正文")
            dim("议程与阵容信息量", ag_sc, 15, ag_note)
            if rel == 0:
                if CONF_REVIEW_R.search(t) or CONF_REVIEW_R.search(b[:400]):
                    cap = min(cap or 100, 40)
                    dims[-1][3] += "；Gate：评审类通稿无发布物→封顶40"
                elif infl_hit:
                    cap = min(cap or 100, 68)
                    dims[-1][3] += "；Gate：有影响力无发布物→封顶68"
                else:
                    cap = min(cap or 100, 45)
                    dims[-1][3] += "；Gate：影响力与发布物双缺→封顶45"
        else:
            m_auth = AUTH_INST_R.search(src_all) or AUTH_INST_R.search(item["meta"] + " " + t)
            if m_auth:
                a1, a1n = 25, f"权威机构清单✓（{m_auth.group(0)}）"
            elif TOP_SPEAKER_R.search(src_all):
                a1, a1n = 18, "顶级人物发言（院士/创始人/CEO等）"
            elif THINK_TANK_R.search(src_all) or actor:
                a1, a1n = ((18, "研究院所/大学/智库") if THINK_TANK_R.search(src_all)
                            else (12, "域主体清单命中"))
            else:
                a1, a1n = 6, "自媒体/信源未标注"
            n_depth = len(set(DEPTH_R.findall(src_all)))
            a2, a2n = ((25, f"结构化深度词{n_depth}类✓") if n_depth >= 3 else
                       ((16, f"深度词{n_depth}类") if n_depth else (6, "无结构化深度词")))
            if n_unit_sf >= 3 and CALIB2_R.search(src_all):
                a3, a3n = 25, f"数值{n_unit_sf}处+基期/预测口径✓"
            elif n_unit_sf >= 1:
                a3, a3n = 14, f"数值{n_unit_sf}处（口径词未检出）"
            else:
                a3, a3n = 6, "无数值"
            dom_sc2 = 15 if tcore2 else (10 if tcore1 else (5 if dparts["body"] > 0 else 2))
            strategic = bool(STRATEGIC_TOPIC_R.search(src_all))
            distinct = bool(DISTINCT_VIEW_R.search(src_all))
            topic_sc = 15 if strategic and distinct else (10 if strategic else 0)
            topic_note = ("战略热点+差异化观点" if topic_sc == 15 else
                          ("战略热点（观点差异性未充分检出）" if topic_sc else "未命中"))
            A = a1 + a2 + a3 + dom_sc2 + topic_sc
            buzz_n = len(set(BUZZ_R.findall(src_all)))
            pop_n = len(set(POPSCI_R.findall(src_all)))
            B_on = buzz_n >= 1 and pop_n >= 1
            if B_on:
                b1 = 40 if buzz_n >= 2 else 24
                b2 = 18 if pop_n >= 2 else 12
                b3 = 20 if tcore2 else (13 if tcore1 else (6 if dparts["body"] > 0 else 2))
                b4 = 17 if n_unit_sf >= 2 else (12 if n_unit_sf >= 1 else 0)
                B = b1 + b2 + b3 + b4
            else:
                B = 0
            dim("软信息通道", 0, 0,
                f"T22/T23：S=max(分析质量A={A}, 话题监测B={B if B_on else '未启用'})，不乘TRL")
            if A >= B:
                dim("信源权威度", a1, 25, a1n)
                dim("结构化深度", a2, 25, a2n)
                dim("数据口径", a3, 25, a3n)
                dim("域关联", dom_sc2, 15, "题名核心词≥2/1/仅正文")
                if topic_sc:
                    dim("战略议题与观点差异", topic_sc, 15, topic_note)
                dims[0][3] += " → 取A（分析质量）"
            else:
                dim("话题热度", b1, 40, f"话题词{buzz_n}类命中")
                dim("科普/解读属性", b2, 18, f"属性词{pop_n}类命中")
                dim("域关联", b3, 20, "题名核心词≥2/1/仅正文")
                dim("数据支撑", b4, 17, f"数值{n_unit_sf}处")
                dims[0][3] += " → 取B（话题监测；不等同技术突破）"
            if INDUSTRY_AI_R.search(t) and not re.search(r"脱碳|减排|降碳|低碳|零碳", t):
                cap = min(cap or 100, 79)
                dims[0][3] += "；Gate：题名主体为AI/创业，行业脱碳仅属案例→封顶79"
            if A < 40 and not B_on:
                cap = min(cap or 100, 45)
    elif cid == "card_tech":
        dim("瓶颈相关性", 30 if tcore2 else (20 if tcore1 else (15 if dparts["body"] > 0 else 5)), 30,
            "题名核心词≥2/1/仅正文（CORE/SECONDARY/EMERGING 词面近似）")
        if review:
            dim("指标表现×域基线", 6, 25, "综述/观点题名：不以摘录参数冒充瓶颈突破，走期刊档位通道")
        elif first_t and dom_unit:
            dim("指标表现×域基线", 25, 25, "首发/纪录+域单位≈超基线档(幅度不可判)")
        elif relay and first_t and gen_unit and RELAY_GAIN_R.search(t + "\n" + b[:1000]):
            dim("指标表现×域基线", 20, 25, "媒体转述：纪录/首发+通用单位+量化倍数对比≈自报超基线")
        elif dom_unit:
            dim("指标表现×域基线", 14, 25, "数值+域单位≈达基线")
        elif gen_unit:
            dim("指标表现×域基线", 8, 25, "数值+通用单位≈未达标/口径不可比")
        else:
            dim("指标表现×域基线", na_perf, 25, f"无数值 NA（TRL{trl or '未判'}）")
        if review:
            dim("新颖性/机理", 8, 25, "综述/观点题名：新颖性不由摘要转述词推断")
        elif MECH_R.search(txt):
            dim("新颖性/机理", 25, 25, "机理/机制/新路线词命中（TRL1-3 主导维度）")
        elif relay and MODEL_INSIGHT_R.search(t + "\n" + b):
            dim("新颖性/机理", 22, 25, "顶级期刊模型/战略研究：量化机制与路径洞见")
        elif INCR_R.search(txt):
            dim("新颖性/机理", 15, 25, "显著改进词命中")
        else:
            dim("新颖性/机理", 8, 25, "增量改进/常规表征")
        if lit:
            qn, q = _journal_tier(item)
            author_cite = item.get("author_cite")
            # 预留字段：当前 RSS 无通讯作者被引量，None 时严格不调整；未来接库后仅在 20 分内倾斜。
            cite_bonus = 2 if isinstance(author_cite, (int, float)) and author_cite >= 10000 \
                else (1 if isinstance(author_cite, (int, float)) and author_cite >= 1000 else 0)
            q = min(20, q + cite_bonus)
            cite_note = "；通讯作者被引量缺失，不调整" if author_cite is None \
                else f"；通讯作者被引量={author_cite:g}，档内+{cite_bonus}"
            dim("证据质量", q, 20, f"{qn}{cite_note}；公式=f(期刊档, 媒体转述, DOI)")
        elif relay:
            qn, q = _relay_journal_tier(item)
            dim("证据质量", q, 20, f"{qn}；公式=f(期刊档, 媒体转述, DOI)")
        else:
            dim("证据质量", 6, 20, "新闻/公众号≈单方宣称；公式=f(期刊档, 媒体转述, DOI)")
    elif cid == "card_validation":
        if VALID_SCALE_R.search(txt):
            dim("验证尺度", 30, 30, "真实工况/示范级/全尺寸")
        elif PILOT_R.search(txt):
            dim("验证尺度", 20, 30, "中试级/缩放系统")
        else:
            dim("验证尺度", 12, 30, "实验室台架/小样")
        validation_first = first_t or bool(FIRST_R.search(b[:1000]))
        if validation_first and metric_eff:
            dim("结果量化×域基线", 25, 25, "首发/纪录+域单位≈超基线档（草案域以通用规模单位兜底）")
        elif metric_eff:
            dim("结果量化×域基线", 14, 25, "数值+域单位≈达基线（草案域以通用规模单位兜底）")
        elif gen_unit_card:
            dim("结果量化×域基线", 8, 25, "数值+通用单位")
        elif PASS_R.search(txt):
            dim("结果量化×域基线", na_perf, 25, f"定性通过无量化 NA（TRL{trl or '未判'}）")
        else:
            dim("结果量化×域基线", 0, 25, "无数值")
        if THIRD_R.search(txt):
            cond_q, qn = 20, "第三方检测/认证"
        elif JOINT_R.search(txt):
            cond_q, qn = 14, "业主/客户联合验证"
        elif OFFICIAL_VALIDATION_R.search(txt) and VALID_SCALE_R.search(txt):
            cond_q, qn = 12, "具名官方来源+现场/系统级验证（仍低于第三方）"
        else:
            cond_q, qn = 6, "自证/自测"
        dim("条件真实性", cond_q, 20, qn)
        dim("与域瓶颈匹配", 15 if tcore2 else (9 if tcore1 else 3), 15, "题名核心词≥2/1/无关")
        if DUR_R.search(txt):
            dim("持续性证据", 10, 10, "≥1000h/累计/跨季节")
        elif DUR2_R.search(txt):
            dim("持续性证据", 5, 10, "持续时间较短")
        elif MULTI_COND_STABLE_R.search(txt):
            dim("持续性证据", 6, 10, "启停/负载变化等多工况稳定；未披露长周期时长")
        elif DELIVERED_ACCEPTED_R.search(txt):
            dim("持续性证据", 5, 10, "完成调试/验收并交付或发运：跨环节工程证据（不等同长期运行）")
        else:
            dim("持续性证据", 0, 10, "单点瞬时")
        if cond_q == 6 and not (dom_unit or gen_unit_card):
            cap = min(cap or 100, 45)  # Gate：自证+无量化 → 封顶 45（S3 组：无数值判定改卡内口径）
    elif cid == "card_production":
        if STRONG_EV_R.search(t) or NEG_EV_R.search(t) or body_strong:
            tr_, tn = 35, "投产/满产/并网或负向突变"
        elif RAMP_R.search(txt):
            tr_, tn = 25, "爬坡/扩产/技改"
        elif ROUT_RUN_R.search(txt):
            tr_, tn = 10, "常规运行通报"
        else:
            tr_, tn = 5, "计划/预告"
        if not (dom_unit or gen_unit_card):
            tr_ = min(tr_, 25)  # NA 规则：未披露规模 → 跃迁维度封顶 25（S3 组：改卡内数值口径）
            tn += "（未披露规模→封顶25）"
        dim("状态跃迁/突变幅度", tr_, 35, tn)
        if SCALE_ABS_R.search(txt) and scale_eff:
            dim("规模×域量级", 25, 25, "极值/首发词+域单位≈≥域典型量级（草案域以通用规模单位兜底）")
        elif scale_eff:
            dim("规模×域量级", 15, 25, "域单位数值≈域量级 30%-1 倍（草案域以通用规模单位兜底）")
        elif gen_unit_card:
            dim("规模×域量级", 8, 25, "通用数值≈低于域量级 30%（含中文工程单位）")
        else:
            dim("规模×域量级", 0, 25, "未披露")
        yv = 15 if (YIELD_R.search(txt) and n_unit) else (7 if YIELD_R.search(txt) else 0)
        dim("良率/利用率/可靠性披露", yv, 15, {15: "披露具体数值", 7: "定性描述", 0: "未披露"}[yv])
        dim("运行时长/出货证据", 15 if DUR_R.search(txt) else (7 if DUR2_R.search(txt) else 0), 15,
            "累计运行/出货 15 · 单点时点 7 · 无 0")
        dim("主体产线地位", 10 if actor else (6 if FIRM_R.search(txt) else 3), 10, "域主体清单/公司词/未知")
        if trl in (8, 9) and tr_ == 10:
            cap = min(cap or 100, 30)  # Gate：TRL8-9 常规运行通报 → 封顶 30×权重
    elif cid == "card_project":
        # 评分卡修订（2026-09-11 五次修订·S3 组）：
        # ① 阶段跃迁阶梯扩为 35/25/22/18/12/5：补"交付"强事件词（原注记有交付但词面缺失）；
        #   新增 22 档验证里程碑（试飞/载人/道路测试/路试/示范运行/完成试验/进入市场——
        #   原 5 档"意向/传闻"误收里程碑事件）与 18 档投资落定（投资约+金额/持股/合资，
        #   高于备案规划 12 档：资金落定=前期确定性最强态），档值 TODO(回测)
        # ② 工程确定性 20 档补"强事件事实发生"（投产/交付已发生=确定性最高，原落到 4 档
        #   "仅宣布"并触发 Gate≤45 误伤——用户反馈 #21/#24）；12 档验证里程碑完成；
        #   10 档补投资落定
        # ③ 规模×域量级：E 草案域以通用规模单位兜底（scale_eff，同上）
        # ④ 领域意义首发词检索窗 title→正文前 1000 字（"全球首套…"常在正文首句，非题名）
        # ⑤ 新增 Gate：开工/吊装类施工动态（无投运证据）封顶 75 TODO(回测)——用户反馈 #1：
        #   吊装+大数字+中标叠加曾到 82 高档，实质是项目在建动态
        scarce_ldes_plan = bool(SCARCE_LDES_PROJECT_R.search(txt)
                                and LDES_DURATION_R.search(txt)
                                and PROJECT_COMMIT_R.search(txt)
                                and (dom_unit or gen_scale_card))
        early_title = bool(re.search(r"备案|公示", t)) and not bool(OPERATION_EV_R.search(t))
        yard_title_only = bool(YARD_R.search(t) or MECH_COMPLETE_R.search(t)) and not bool(OPERATION_EV_R.search(t))
        if early_title:
            pj, pn = 12, "备案/公示（前期程序，未开工）"
        elif scarce_ldes_plan and not OPERATION_EV_R.search(t):
            pj, pn = 18, "稀缺长时路线+量化规模/时长+具名合作/选址（仍属计划阶段）"
        elif yard_title_only:
            pj, pn = 25, "开工/封顶/主设备吊装/建成中交（未投运）"
        elif STRONG_EV_R.search(t) or body_strong:
            pj, pn = 35, "投产/并网/交付运行"
        elif YARD_R.search(txt):
            pj, pn = 25, "开工/封顶/主设备吊装/建成中交（未投运）"
        elif MILESTONE_EV_R.search(txt):
            pj, pn = 22, "验证里程碑（试飞/路试/示范运行/完成试验/市场进入）TODO(回测)"
        elif INVEST_EV_R.search(txt):
            pj, pn = 18, "投资落定（投资额/持股/合资披露，未开工）TODO(回测)"
        elif re.search(r"备案|规划|签约|核准|中标", txt):
            pj, pn = 12, "备案/规划/签约（未开工）"
        else:
            pj, pn = 5, "意向/传闻"
        dim("阶段跃迁", pj, 35, pn)
        if SCALE_ABS_R.search(txt) and scale_eff:
            dim("规模×域量级", 25, 25, "极值/首发+域单位≈≥域典型量级（草案域以通用规模单位兜底）")
        elif scale_eff:
            dim("规模×域量级", 15, 25, "域单位数值≈30%-1 倍（草案域以通用规模单位兜底）")
        elif gen_unit_card:
            dim("规模×域量级", 8, 25, "通用数值≈<30%（含中文工程单位）")
        elif (STRONG_EV_R.search(t) or body_strong) and (FIRST_R.search(t) or FIRST_R.search(b[:1000])):
            dim("规模×域量级", 15, 25, "首个商业投产/运行但规模未披露：以部署稀缺性代理中档 TODO(回测)")
        else:
            dim("规模×域量级", 0, 25, "未披露")
        if early_title:
            det, dtn = 10, "备案/公示程序已落实（未开工）"
        elif scarce_ldes_plan and not OPERATION_EV_R.search(t):
            det, dtn = 12, "具名业主/企业共建与选址，计划确定性高于一般宣布"
        elif EPC_R.search(txt) or (STRONG_EV_R.search(t) or body_strong) and not yard_title_only:
            det, dtn = 20, "中标/EPC/审批/正式合同 或 投产/交付事实已发生"
        elif MILESTONE_EV_R.search(txt):
            det, dtn = 12, "验证里程碑完成（试飞/路试/试验）TODO(回测)"
        elif re.search(r"签约|开工|奠基|融资", txt) or INVEST_EV_R.search(txt):
            det, dtn = 10, "部分落实（签约/开工/投资落定）"
        else:
            det, dtn = 4, "仅宣布"
        dim("工程确定性", det, 20, dtn)
        dim("领域意义", 20 if (scarce_ldes_plan or
            (tcore1 and (FIRST_R.search(t) or FIRST_R.search(b[:1000]) or "示范" in txt)))
            else (12 if tcore1 else 5), 20,
            "核心瓶颈路线+首发/示范 20 · 核心 12 · 常规 5（首发词认题名或正文前1000字）")
        if det <= 4:
            cap = min(cap or 100, 45)  # Gate：仅宣布 → 封顶 45（S3 组：确定性分档修复后仅剩真"仅宣布"）
        if scarce_ldes_plan and not OPERATION_EV_R.search(t):
            cap = min(cap or 100, 69)  # 稀缺路线的规划信号可进中档，但未开工/投运不得进高档
        if pj == 25:
            cap = min(cap or 100, 75)  # Gate：开工/吊装类施工动态（无投运证据）→ 封顶 75 TODO(回测)
        if re.search(r"备案|公示", t) and pj <= 12:
            cap = min(cap or 100, 55)  # Gate：备案/公示仅属前期程序 → 封顶 55 TODO(回测)
    elif cid == "card_financing":
        fin_verified_tech = bool(FIN_KEY_METRIC_R.search(txt) and FIN_TECH_VERIFY_R.search(txt))
        fin_trend_agg = bool(FIN_TREND_AGG_R.search(txt))
        if AMT_BIG_R.search(txt):
            dim("金额×域基线异常度", 15, 35, "亿级金额≈常规档(1-3×域基线，异常度不可判)")
        elif AMT_SMALL_R.search(txt):
            dim("金额×域基线异常度", 8, 35, "小额(万元级)")
        else:
            dim("金额×域基线异常度", 0, 35, "金额未披露")
        if EQ_ROUND_R.search(txt) and USE_R.search(txt):
            dim("轮次与阶段匹配", 25, 25, "股权轮次推进+投向产能/中试/研发（推进明显）")
        elif EQ_ROUND_R.search(txt):
            dim("轮次与阶段匹配", 15, 25, "股权轮次推进（投向未明）")
        elif CAP_OP_R.search(txt):
            dim("轮次与阶段匹配", 10, 25, "资本运作（战略增资/定增/募资/IPO），无轮次推进语义 TODO(回测)")
        else:
            dim("轮次与阶段匹配", 8, 25, "轮次不明/错配不可判")
        if NATION_R.search(txt):
            dim("资本主体", 20, 20, "国家级/战略/产业链巨头词命中")
        elif FIN_R.search(txt):
            dim("资本主体", 12, 20, "一般投资机构词命中")
        else:
            dim("资本主体", 5, 20, "不明/个人")
        dim("用途与域瓶颈匹配", 20 if (tcore1 and USE_R.search(txt)) else (10 if USE_R.search(txt) else 4), 20,
            "投向核心瓶颈词 20 · 一般研发/扩产 10 · 未说明 4")
        if not (AMT_BIG_R.search(txt) or AMT_SMALL_R.search(txt)):
            cap = min(cap or 100, 50)  # Gate：金额未披露 → 封顶 50
        if not (first_t or TECH_BREAK_FACT_R.search(b[:1000]) or MERGER_MAJOR_R.search(t + "\n" + b[:1000])):
            cap = min(cap or 100, 75)  # 无技术突破/头部重大合并，不得进高档 TODO(回测)
        if not fin_verified_tech and not fin_trend_agg and not MERGER_MAJOR_R.search(t + "\n" + b[:1000]):
            cap = min(cap or 100, 55)
            # 单笔融资只作为趋势样本；路线名、扩产规模与企业自述不是独特/颠覆性技术证据。
        if re.search(r"拟|计划|将", t) and re.search(r"定增|募资|融资|增资|IPO", t):
            cap = min(cap or 100, 45)  # 拟融资仅为前期事件 TODO(回测)
    elif cid == "card_procurement":
        if actor and NATION_R.search(txt):
            dim("客户层级", 30, 30, "域主体+国家级/头部业主词")
        elif actor:
            dim("客户层级", 18, 30, "域主体清单命中（层级词面不可判）")
        else:
            dim("客户层级", 8, 30, "未知客户")
        if FIRST_R.search(t) and (AMT_BIG_R.search(txt) or dom_unit):
            dim("数量/金额×域基线", 25, 25, "首发词+大额≈战略量级")
        elif AMT_BIG_R.search(txt) or dom_unit:
            dim("数量/金额×域基线", 15, 25, "域典型量级")
        elif gen_unit:
            dim("数量/金额×域基线", 7, 25, "小额")
        else:
            dim("数量/金额×域基线", 7, 25, "量级未披露按小额")
        if re.search(r"中标|公示|合同|成交|定标|框架协议", txt) and not re.search(r"框架协议", txt):
            if re.search(r"候选人公示|预中标|成交候选人", txt):
                pay, payn = 14, "中标/成交候选人公示（未定标）TODO(回测)"
            else:
                pay, payn = 20, "中标公示/正式合同/已交付"
        elif re.search(r"框架协议", txt):
            pay, payn = 10, "框架协议"
        else:
            pay, payn = 4, "意向/谅解备忘录"
        dim("付费真实性", pay, 20, payn)
        dim("重复订单/复购", 15 if re.search(r"复购|加单|再获|续签|追加|二次", txt) else 8, 15,
            "复购/加单 15 · 首单 8")
        dim("领域阶段意义", 10 if FIRST_R.search(t) else 4, 10, "首发/首次商业采用 10 · 常规 4")
        if re.search(r"意向|备忘录|MOU", txt) and pay == 4:
            cap = min(cap or 100, 35)  # Gate：仅意向 → 封顶 35
        if BID_SVC_R.search(txt) or (re.search(r"设计", txt) and not EPC_LIKE_R.search(txt)):
            cap = min(cap or 100, 45)  # 监理/咨询等服务类招投标封顶低档 TODO(回测)
    elif cid == "card_market":
        pcts = [float(m) for m in PCT_NEAR_R.findall(txt)]
        mx_pct = max(pcts) if pcts else 0
        if mx_pct >= 50:
            dim("变化量级×域基线", 35, 35, f"变化≈{mx_pct:g}% ≥±50%")
        elif mx_pct >= 20:
            dim("变化量级×域基线", 25, 35, f"变化≈{mx_pct:g}% ∈±20-50%")
        elif mx_pct >= 10:
            dim("变化量级×域基线", 15, 35, f"变化≈{mx_pct:g}% ∈±10-20%")
        elif pcts:
            dim("变化量级×域基线", 6, 35, f"变化≈{mx_pct:g}% <±10%")
        else:
            dim("变化量级×域基线", 0, 35, "无数值变化")
        dim("持续性", 20 if STRUCT_R.search(txt) else 8, 20, "结构性/格局级 20 · 事件性脉冲 8")
        dim("覆盖范围", 20 if SCOPE_ALL_R.search(txt) else 8, 20, "全域/全球 20 · 区域/单环节 8")
        has_base = bool(BASE_R.search(txt))
        dim("可比口径", 15 if has_base else 6, 15, "有基期口径 15 · 口径含糊 6")
        dim("方向与预警线索", 10 if ALERT_R.search(txt) else 0, 10, "断供/管制/安全连锁 10")
        if not pcts or not has_base:
            cap = min(cap or 100, 30)  # Gate：无数值/无基期 → 封顶 30
        if not (first_t or TECH_BREAK_FACT_R.search(b[:1000]) or MERGER_MAJOR_R.search(t + "\n" + b[:1000])):
            cap = min(cap or 100, 75)
        if STAT_PERIOD_R.search(txt) and not INFLECT_STRONG_R.search(t):
            cap = min(cap or 100, 60)  # 常规周期统计不按结构性拐点评高档 TODO(回测)
    elif cid == "card_supply":
        if CHoke_R.search(txt):
            dim("节点关键性", 30, 30, "独家/卡脖子词命中")
        elif SUP_MAJOR_R.search(txt):
            dim("节点关键性", 18, 30, "主要供应商（多源之一）")
        else:
            dim("节点关键性", 8, 30, "边缘环节")
        if CUT_R.search(txt):
            dim("事件类型", 25, 25, "断供/禁运/出口管制")
        elif SUBST_R.search(txt):
            dim("事件类型", 20, 25, "国产替代/第二源")
        elif LTA_R.search(txt):
            dim("事件类型", 12, 25, "长协/框架锁定")
        else:
            dim("事件类型", 5, 25, "常规供货调整")
        dim("影响范围", 25 if re.search(r"全行业|全域|多家|全球", txt) else 10, 25, "波及全域/多家头部 25 · 单客户 10")
        if REPL_OK_R.search(txt):
            dim("可替代性证据", 20, 20, "替代路线+验证状态")
        elif REPL_CLAIM_R.search(txt):
            dim("可替代性证据", 8, 20, "宣称可替代未验证")
        else:
            dim("可替代性证据", 4, 20, "未说明（下限 4）")
        if RUMOR_R.search(txt) and not FIRM_R.search(txt):
            cap = min(cap or 100, 30)  # Gate：传闻级断供（无主体）→ 封顶 30 转人工
        if not CUT_R.search(txt) and not (first_t or TECH_BREAK_FACT_R.search(b[:1000])
                                          or MERGER_MAJOR_R.search(t + "\n" + b[:1000])):
            cap = min(cap or 100, 75)
    elif cid == "card_enterprise":
        if BROKE_R.search(txt):
            dim("突变幅度", 35, 35, "破产/接管/重组/退出（负向高情报价值）")
        elif SWING_R.search(txt):
            dim("突变幅度", 28, 35, "盈亏反转/大幅超预期")
        else:
            dim("突变幅度", 10, 35, "常规业绩波动")
        dim("主体地位", 25 if actor else (12 if FIRM_R.search(txt) else 5), 25, "域主体清单/公司词/外围")
        dim("财务口径", 20 if ROUTINE_R.search(txt) else 8, 20, "审计报表/公告词 20 · 媒体估算 8")
        dim("与域阶段关联", 20 if (tcore1 and (BROKE_R.search(txt) or SWING_R.search(txt))) else 6, 20,
            "直接反映该路线商业化成败 20 · 一般经营 6")
        if not BROKE_R.search(txt) and not (first_t or TECH_BREAK_FACT_R.search(b[:1000])
                                            or MERGER_MAJOR_R.search(t + "\n" + b[:1000])):
            cap = min(cap or 100, 75)
    elif cid == "card_policy":
        policy_project_call = bool(POLICY_PROJECT_CALL_R.search(t)
                                   and OFFICIAL_POLICY_DOC_R.search(t + "\n" + b[:1200]))
        if MANDATE_R.search(txt):
            pstr, psn = 35, "强制准入/禁令/配额"
        elif STD_ACCESS_R.search(txt):
            pstr, psn = 28, "准入/分级类标准·定门槛改变市场结构"  # TODO(回测)
        elif SUBSID_R.search(txt):
            pstr, psn = 22, "大额补贴/税收"
        elif POLICY_MARKET_MECH_R.search(txt):
            pstr, psn = 18, "正式市场交易/匹配/监管机制上线"
        elif POLICY_DEPLOY_R.search(txt):
            pstr, psn = 18, "部署执行类·专项行动/设备更新改造"  # TODO(回测)
        elif policy_project_call and POLICY_ROUTE_REQ_R.search(txt):
            pstr, psn = 18, "项目申报通知含明确技术路线约束（仍非项目落地）"
        else:
            pstr, psn = 8, "指导性/吹风"
        if re.search(r"征求.{0,12}意见", txt):  # Gate：征求意见稿 → 强度维度封顶 12
            pstr, psn = min(pstr, 12), psn + "（征求意见稿→强度封顶12）"
        dim("影响强度", pstr, 35, psn)
        dim("覆盖范围", 25 if POLICY_SCOPE_R.search(txt) else 12, 25,
            "全国性/多部门联合/全国性标准 25 · 区域/试点/省级 12")
        blank_hit = FIRST_DOC_R.search(txt) or BLANK_NEW_R.search(txt)
        dim("填补空白", 20 if (blank_hit and RULE_WORD_R.search(txt)) else 10, 20,
            "首个/全新规则词+规则载体 20 · 既有修订/常规 10")
        dim("与域瓶颈匹配", 20 if tcore1 else 8, 20, "题名核心词命中 20 · 间接相关 8")
        if policy_project_call:
            cap = min(cap or 100, 65 if POLICY_ROUTE_REQ_R.search(txt) else 55)
    elif cid == "card_talent":
        if TOP_TALENT_R.search(txt):
            dim("人物/团队层级", 30, 30, "带头人/创始人/院士词命中")
        elif MID_TALENT_R.search(txt):
            dim("人物/团队层级", 15, 30, "知名高管/骨干")
        else:
            dim("人物/团队层级", 5, 30, "一般人事")
        dim("与域关键能力关联", 40 if tcore2 else (20 if tcore1 else 8), 40, "题名核心词≥2/1/关联弱")
        dim("迁移规模", 30 if TEAM_SCALE_R.search(txt) else (15 if "小组" in txt else 8), 30,
            "成建制团队/研发中心 30 · 小组 15 · 单人 8")
    raw = sum(d[1] for d in dims)
    # 稀缺长时路线项目若同时给出量化时长/规模以及具名合作或选址，虽然仍处于
    # 规划阶段、不得进入高档，但其技术路线市场验证信号已高于普通项目宣布。
    # 这里使用机制级 medium 下限，而不是按具体链接加分。
    if cid == "card_project" and scarce_ldes_plan and not OPERATION_EV_R.search(t):
        raw = max(raw, 60)
    return raw, dims, trl, w, cap

# ---------------- 读取三源（窗口过滤） ----------------
def _d_from_str(s):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None

def read_rows():
    rows = []
    for p in sorted(glob.glob(os.path.join(SRC_ROOT, "news-spider", "data", "articles-2026-06-*.csv"))):
        fday = _d_from_str(os.path.basename(p).replace("articles-", ""))
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            d = _d_from_str(r.get("published_at")) or fday
            if not (W0 <= d <= W1):
                continue
            raw_body = r.get("content") or ""
            body, body_prep = preprocess_body(raw_body, (r.get("title") or "").strip())
            rows.append({"src": "news-spider", "date": d.isoformat(), "title": (r.get("title") or "").strip(),
                         "url": r.get("url") or "", "meta": r.get("source_name") or "", "body": body,
                         "doi": "", "body_prep": body_prep,
                         "content_quality": "full" if raw_body.strip() else "empty"})
    for p in sorted(glob.glob(os.path.join(SRC_ROOT, "wechat-daily-news-csv", "csv", "2026-06-*.csv"))):
        fday = _d_from_str(os.path.basename(p))
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            d = _d_from_str(r.get("publish_time")) or fday
            if not (W0 <= d <= W1):
                continue
            # 抓取正文缺失时优先用 content_preview，再退到短 digest；同时保留来源层级，
            # 防止把摘要当完整正文强行精确评分。
            raw_full = r.get("clean_text") or ""
            raw_preview = r.get("content_preview") or ""
            raw_digest = r.get("digest") or ""
            raw_body = raw_full or raw_preview or raw_digest
            quality = "full" if raw_full.strip() else ("preview" if raw_preview.strip()
                                                       else ("digest" if raw_digest.strip() else "empty"))
            body, body_prep = preprocess_body(raw_body,
                                              (r.get("title") or "").strip())
            rows.append({"src": "wechat", "date": d.isoformat(), "title": (r.get("title") or "").strip(),
                         "url": r.get("url") or "", "meta": r.get("account_name") or "", "body": body,
                         "doi": "", "body_prep": body_prep, "content_quality": quality})
    for p in sorted(glob.glob(os.path.join(SRC_ROOT, "literature-rss-spider", "output",
                                           "news_with_abstract_2026-06-*.csv"))):
        fday = _d_from_str(os.path.basename(p).replace("news_with_abstract_", ""))
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            d = _d_from_str(r.get("pub_date")) or fday
            if not (W0 <= d <= W1):
                continue
            raw_body = r.get("abstract") or ""
            body, body_prep = preprocess_body(raw_body, (r.get("title") or "").strip())
            rows.append({"src": "literature", "date": d.isoformat(), "title": (r.get("title") or "").strip(),
                         "url": r.get("link") or "", "meta": r.get("source") or "", "body": body,
                         "doi": r.get("doi") or "", "body_prep": body_prep,
                         "content_quality": "abstract" if raw_body.strip() else "empty"})
    return rows

# ---------------- 分类 ----------------
def score_domain(item, dom):
    title, body = item["title"], item["body"]
    # 规则口径：按命中次数计（标题核心词 1 次 28 / ≥2 次 40；正文核心词每次 +3 封顶 18；扩展词同理）
    # 文献源：并入 docx 文献规则英文召回层（同核心词档计分，证据词带 ※）
    core_r = dom["core_r"] + dom["lit_r"] if item["src"] == "literature" else dom["core_r"]
    t_c = sum(len(rx.findall(title)) for _t, rx in core_r)
    t_e = sum(len(rx.findall(title)) for _t, rx in dom["ext_r"])
    # 文献叶术语既然声明并入核心词档，摘要证据也应进入 D 分，而非只展示路径。
    b_c = sum(len(rx.findall(body)) for _t, rx in core_r)
    b_e = sum(len(rx.findall(body)) for _t, rx in dom["ext_r"])
    t_sc = max(28 if t_c >= 1 else 0, 40 if t_c >= 2 else 0,
               10 if t_e >= 1 else 0, 18 if t_e >= 2 else 0)
    b_sc = min(18, 3 * b_c) + min(12, b_e)
    tc = [t for t, rx in core_r if rx.search(title)]
    bc = [t for t, rx in core_r if rx.search(body)]
    te = [t for t, rx in dom["ext_r"] if rx.search(title)]
    be = [t for t, rx in dom["ext_r"] if rx.search(body)]
    actor = [t for t, rx in dom["actors_r"] if rx.search(title) or rx.search(body)]
    a_sc = 15 if actor else 0
    route_hit = ""
    route_sc = 0
    route_rx = DOMAIN_ROUTE_R.get(dom["no"])
    if route_rx:
        rm = route_rx.search(title)
        if rm:
            # v0.97 D-G04：题名排他路线是“对象身份”证据，不是普通辅助词。
            # 30（题名对象）+40（专属路线）=70，确保专属叶可直接进入主域候选；
            # 仍要求复合术语命中，单独“储能/电池”不会触发。
            route_hit, route_sc = rm.group(0), 40
            t_sc = max(t_sc, 30)
    m_sc, m_hit = 0, ""
    if NUM_UNIT_R.search(title) or NUM_UNIT_R.search(body):
        m_sc, m_hit = 7, "数值+通用单位"
        for u in dom["units"]:
            if u and re.search(r"\d+(?:\.\d+)?\s*" + re.escape(u), title + body, re.I):
                m_sc, m_hit = 15, f"数值+域单位({u})"
                break
    guard = ""
    # 用户反馈 #5：LED/光电器件不能仅凭“钙钛矿”被吸入 D01。题名是研究对象的强证据；
    # 若题名同时含 solar/photovoltaic/光伏/太阳能，则太阳能对象优先，不触发负条件。
    led_dominant = (_led_evidence(title) > 0 and not SOLAR_SIDE_R.search(title)) or \
                   (not SOLAR_SIDE_R.search(title) and not SOLAR_SIDE_R.search(body)
                    and _led_evidence(body) >= 3)
    if dom["no"] == "D01" and led_dominant:
        t_sc = b_sc = a_sc = m_sc = route_sc = 0
        tc, bc, te, be, actor, m_hit = [], [], [], [], [], ""
        route_hit = ""
        guard = "D01负条件:LED/光电器件证据主导且题名无太阳能对象→排除光伏；路由E99待建光电器件域"
    d = min(100, t_sc + b_sc + a_sc + m_sc + route_sc)
    return d, {"title": t_sc, "body": b_sc, "actor": a_sc, "metric": m_sc,
               "core_hits": (tc + bc)[:6], "ext_hits": (te + be)[:4], "actor_hits": actor[:2],
               "metric_hit": m_hit, "route": route_sc, "route_hit": route_hit,
               "core_title_n": t_c, "core_body_n": b_c, "domain_guard": guard}

def classify_type(item):
    title, body = item["title"], item["body"]
    lit = item["src"] == "literature"
    # ③来源先验证据化：正文前段论文证据→科研先验；题名是产业事件（推出/交付/建成…）时不信背景引用
    #   2026-09-11 S1 组：题名顶刊书名号（《Nature/Science…》/登顶《…》）同为论文载体证据
    source_paper_ev = bool(SOURCE_PAPER_R.search(body))
    research_ev = (bool(PAPER_EV_R.search(body[:600])) or bool(PAPER_EXPLICIT_R.search(body))
                   or bool(PAPER_CARRIER_EXT_R.search(body))
                   or source_paper_ev
                   or bool(TITLE_PAPER_R.search(title))) \
        and not INDUS_TITLE_R.search(title)
    official_platform = bool(OFFICIAL_PLATFORM_TITLE_R.search(title)
                             and OFFICIAL_PLATFORM_BODY_R.search(body[:1000]))
    tech_explainer = bool(len(body) >= 500 and not RD_PLAN_OBJECT_R.search(title + "\n" + body[:800])
                          and TECH_BOTTLENECK_R.search(body[:1600])
                          and TECH_SOLUTION_R.search(body[:1600]))
    scores = []
    for t in TYPES:
        tt, bt = TYPE_TRIG[t["id"]]
        fam = 40 if any(rx.search(title) for rx in tt) else (25 if any(rx.search(body) for rx in bt) else 0)
        # T01 正文触发词证据化（2026-09-11 五次修订·S1 组）：非文献源正文泛词（实验/表征/样品/对比）
        #   过宽——会议预告模板"设备、样品、资料"、材料文"表征材料"、机构名"XX实验室"即可命中，
        #   媒体综述稿被推向 T01（#7/#10 根因）。须论文载体证据（research_ev）联判才计 fam25。
        if t["id"] == "T01" and fam == 25 and not lit and not research_ev:
            fam = 0
        if lit or research_ev:
            prior = 10 if RESEARCH_NAME_R.search(t["name"]) else 0
        else:
            prior = 10 if INDUSTRY_NAME_R.search(t["name"]) else 0
        ev = 0
        if STAGE_STRONG_R.search(title) or STAGE_STRONG_R.search(body[:500]):
            ev = 15
        elif STAGE_WEAK_R.search(title) or STAGE_WEAK_R.search(body[:500]):
            ev = 8
        if ev and FUTURE_R.search(title):
            ev = min(ev, 5)  # 拟建/将建类前期信号降档
        nu = 15 if NUM_UNIT_R.search(title) or NUM_UNIT_R.search(body) else 0
        scores.append((prior + fam + ev + nu, t, {"prior": prior, "family": fam, "event": ev, "numeric": nu}))
    scores.sort(key=lambda x: -x[0])
    sc, t, parts = scores[0]
    # ④近分双候选：分差 <10 不强行 argmax 掩盖，标记低置信转人工
    #   仅在 sc≥35（次型及以上）生效——待定/域外条目各类型普遍同分 0，标记无意义
    alt = None
    # 文献 RSS 是期刊题录专源，来源即 T01 载体证据；不再与 T02 的科研先验形成伪低置信。
    if lit:
        sc, t, parts = next(row for row in scores if row[1]["id"] == "T01")
    elif len(scores) > 1 and sc >= 35 and sc - scores[1][0] < 10 and scores[1][1]["id"] != t["id"]:
        alt = {"id": scores[1][1]["id"], "name": scores[1][1]["name"], "sc": scores[1][0]}
    # ①②③⑦⑧⑨消歧覆写链（2026-09-11 五次修订：题名营销词让位于更强证据；文献库不经此层）
    #   顺序（强→弱）：⑦汇总稿容器 → ②招标/中标 → ⑨期刊全文 → ①发布+报告 → ⑧会议活动 → ③论文证据
    #   ③同 research_ev 守卫：题名产业事件词在时不覆写（正文引用只是背景）
    ov = ""
    if not lit:
        if DIGEST_TITLE_R.search(title) and t["id"] != "T25":
            ov, t = "消歧⑦：题名周刊/合辑类汇总稿 → T25（聚合源标题流，转人工/免评候选）", TYPES_BY_ID["T25"]
        elif RECRUIT_TITLE_R.search(title) and t["id"] != "T21":
            ov, t = "v0.97 C-T05：招聘对象/岗位/应聘证据优先 → T21", TYPES_BY_ID["T21"]
        elif (POLICY_PROJECT_CALL_R.search(title)
              and OFFICIAL_POLICY_DOC_R.search(title + "\n" + body[:1200])
              and t["id"] != "T19"):
            ov, t = "消歧⑫：主管部门正式文件+项目申报/清单报送 → T19 政策法规（非项目落地）", TYPES_BY_ID["T19"]
        elif POLICY_TITLE_STRONG_R.search(title) and not REPORT_TITLE_R.search(title) and t["id"] != "T19":
            ov, t = "v0.97 C-T02：发文机关/联合部门+政策文件动作优先 → T19", TYPES_BY_ID["T19"]
        elif BID_EV_R.search(title) and t["id"] != "T18" and \
                (t["id"] != "T08" or BID_SVC_R.search(title)):
            ov, t = "消歧②：题名招标/中标证据 → T18", TYPES_BY_ID["T18"]
        elif FINANCE_TITLE_STRONG_R.search(title) and not PROJECT_TITLE_STRONG_R.search(title) \
                and t["id"] not in ("T13", "T14"):
            ov, t = "v0.97 C-T06：融资/基金交易对象优先 → T13", TYPES_BY_ID["T13"]
        elif source_paper_ev and t["id"] != "T01" and not INDUS_TITLE_R.search(title) \
                and not re.search(r"招聘|博士后|诚聘|应聘|启事|招贤", title):
            ov, t = "消歧⑬：文末来源栏明确顶级期刊+论文链接 → T01", TYPES_BY_ID["T01"]
        elif t["id"] != "T01" and not INDUS_TITLE_R.search(title) and (
                JOURNAL_TITLE_R.search(title) or CITE_DOI_R.search(body)):
            ov, t = "消歧⑨：期刊论文全文证据（刊名载体/引用本文+DOI）→ T01", TYPES_BY_ID["T01"]
        elif (((PUB_VERB_R.search(title) and REPORT_OBJ_R.search(title)) or REPORT_TITLE_R.search(title))
               or (PUB_VERB_R.search(title) and REPORT_TITLE_R.search(body[:600]))) and t["id"] != "T02":
            ov, t = "消歧①：发布+报告对象联判 → T02", TYPES_BY_ID["T02"]
        elif official_platform and t["id"] != "T19":
            ov, t = "消歧⑩：政府/欧盟正式市场机制平台 → T19", TYPES_BY_ID["T19"]
        elif RD_PLAN_TITLE_STRONG_R.search(title) and t["id"] != "T05":
            ov, t = "v0.97 C-T03：具体科研计划/课题状态 → T05", TYPES_BY_ID["T05"]
        elif PROJECT_TITLE_STRONG_R.search(title) and t["id"] != "T08":
            ov, t = "v0.97 C-T04：具名工程项目状态动作 → T08", TYPES_BY_ID["T08"]
        elif tech_explainer and t["id"] == "T05" and not research_ev:
            ov, t = "消歧⑪：非项目载体的瓶颈—方案技术详述稿 → T23", TYPES_BY_ID["T23"]
        elif CONF_EXT_TITLE_R.search(title) and t["id"] != "T24":
            ov, t = "消歧⑧：题名会议/活动证据 → T24", TYPES_BY_ID["T24"]
        elif t["id"] in ("T09", "T08", "T24", "T05") and research_ev:
            ov, t = "消歧③：正文论文证据 → T01", TYPES_BY_ID["T01"]
    if alt and alt["id"] == t["id"]:
        alt = None  # 强证据覆写后，原次高若已等于最终类型，不显示伪低置信。
    band = "主型" if sc >= 65 else ("次型" if sc >= 35 else "待定")
    fam_label = ""
    for k, rx in FAM_PATTERNS:
        if rx.search(title) or rx.search(body[:500]):
            fam_label = k
            break
    if not fam_label and t.get("families"):
        fam_label = t["families"][0]
    return t["id"], t["name"], sc, band, parts, fam_label, t.get("card", ""), ov, alt


# v0.97 O01–O07：域外必须给出可审计原因，而不是只有一个“域外”标签。
OUT_SCOPE_LABELS = {
    "O01": "真实域外", "O02": "仅背景提及", "O03": "主体过滤",
    "O04": "抓取污染", "O05": "证据不足", "O06": "词表漏项候选",
    "O07": "跨界观察",
}
OUT_SCOPE_CROSS_R = re.compile(
    r"数据中心|算力|人工智能|\bAI\b|芯片|半导体|量子|机器人|无人机|汽车生态|"
    r"气候模型|热管理|液冷|服务器|IDC|航空航天", re.I)


def scope_reason_for(it, dmax, dparts, lit, domain_rule, scope_ignore_reason=""):
    """按 v0.97 域外原因码分流；只用于 disp=域外或主体免评记录。"""
    if scope_ignore_reason:
        return "O03", OUT_SCOPE_LABELS["O03"] + "：" + scope_ignore_reason
    quality = it.get("content_quality", "")
    if quality in ("digest", "empty"):
        return "O05", OUT_SCOPE_LABELS["O05"] + "：仅短摘要/标题或正文为空，不能确认主对象"
    if domain_rule and ("光电器件" in domain_rule or "待建域" in domain_rule):
        return "O06", OUT_SCOPE_LABELS["O06"] + "：对象在行业图景邻近范围，但当前 36 域缺少对应专属域"
    title_score = int((dparts or {}).get("title", 0) or 0)
    body_score = int((dparts or {}).get("body", 0) or 0)
    actor_score = int((dparts or {}).get("actor", 0) or 0)
    metric_score = int((dparts or {}).get("metric", 0) or 0)
    if it.get("body_prep") and title_score == 0 and dmax < 20:
        return "O04", OUT_SCOPE_LABELS["O04"] + "：清洗后只剩低强度正文词，原命中可能来自非主文块"
    if lit and lit.get("target") in (None, "E99") and not lit.get("intarget"):
        return "O01", OUT_SCOPE_LABELS["O01"] + "：文献落在暂不建/E99 叶，未映射到当前 36 个目标域"
    if title_score > 0 or (dparts or {}).get("core_title_n", 0) or domain_rule:
        return "O06", OUT_SCOPE_LABELS["O06"] + "：标题已有目标对象线索但 D<20，进入词表/对象层级复核"
    if OUT_SCOPE_CROSS_R.search(it["title"]):
        return "O07", OUT_SCOPE_LABELS["O07"] + "：标题属于跨界科技/算力主题，但未形成足够的目标能源技术载荷"
    if dmax > 0 and (body_score > 0 or actor_score > 0 or metric_score > 0):
        return "O02", OUT_SCOPE_LABELS["O02"] + "：目标词仅在正文背景、主体清单或通用数字中出现，标题主事件不在该域"
    return "O01", OUT_SCOPE_LABELS["O01"] + "：标题与正文主对象均不属于当前 36 个目标域"


def main():
    rows = read_rows()
    n_raw = len(rows)
    # 去重：规范化标题（跨源/跨日）
    seen, dedup = {}, []
    for it in rows:
        key = re.sub(r"[\W_]+", "", it["title"].lower(), flags=re.U)
        if len(key) < 6:
            key = it["url"]
        if key in seen:
            seen[key]["dup"] += 1
            continue
        it["dup"] = 0
        seen[key] = it
        dedup.append(it)

    out = []
    for it in dedup:
        ds, parts_by = {}, {}
        for dom in DOMS:
            d, parts = score_domain(it, dom)
            ds[dom["no"]], parts_by[dom["no"]] = d, parts
        ranked = sorted(((ds[d["no"]], d, parts_by[d["no"]]) for d in DOMS),
                        key=lambda x: -x[0])
        if ranked and ranked[0][0] > 0:
            dmax, dbest, dparts = ranked[0]
        else:
            dmax, dbest, dparts = 0, None, None
        formula_best, formula_d = dbest, dmax
        domain_rule = ""
        domain_label_override = ""
        # 用户反馈 #12：复合稿按“最终产物/技术难点主体”裁决，不让供能源载体压过制氢主体。
        pdom, pwhy = _subject_priority(it, formula_best, ds, parts_by)
        if pdom is not None and pdom is not dbest:
            dbest, dmax, dparts = pdom, ds[pdom["no"]], parts_by[pdom["no"]]
            domain_rule = pwhy
        # 用户反馈 #5：36 域暂无光电器件，明确排除 D01 后以 E99 待建域展示，避免显示任意低分域。
        led_guard = parts_by.get("D01", {}).get("domain_guard", "")
        if led_guard:
            dbest, dmax = None, 0
            dparts = parts_by["D01"]
            domain_rule = led_guard
            domain_label_override = "E99 光电器件（待建域）"
        # 次高域证据门槛：题名核心/扩展命中，或正文核心词至少 2 个；actor/metric/ext-body 单独不展示。
        second = None
        if domain_rule.startswith("主体优先") and formula_best is not None and formula_best is not dbest:
            second = (formula_best, formula_d)
        else:
            for _sd, _sdom, _sp in ranked:
                if _sdom is dbest or _sd < 20:
                    continue
                if _valid_secondary(_sp):
                    second = (_sdom, _sd)
                    break
        dparts = dparts or {"title": 0, "body": 0, "actor": 0, "metric": 0, "core_hits": [],
                            "ext_hits": [], "actor_hits": [], "metric_hit": "", "domain_guard": ""}
        lit = best_leaf(it, ds) if it["src"] == "literature" else None
        # 题名对象优先（docx 一·3）：挂域叶术语命中题名 → 该叶映射域直判主域
        if lit:
            if lit["target"] not in (None, "E99") and lit["t"] > 0:
                lit["prim"] = lit["target"]
            elif lit.get("intarget") and lit.get("int", 0) > 0:
                lit["prim"] = lit["intarget"]
        tid, tname, tsc, tband, tparts, fam, card, tov, talt = classify_type(it)
        scope_ignore_reason = catl_scope_ignore_reason(it)
        incomplete_reason = ""
        if (it["src"] == "wechat" and it.get("content_quality") in ("digest", "empty")
                and tid in ("T01", "T05", "T23")):
            incomplete_reason = ("正文不足:抓取记录仅含短摘要/标题，技术研究与深度分析不得据此精确评分；"
                                 "保留领域与类型初判，待补抓正文后重评")
        # 汇总稿标记（2026-09-11 五次修订·S1 组）：周刊/合辑类题名正则，独立于分型覆写留存，
        # 供 S5 组"汇总内容提取/暂不参与评分"处置与免评机制对接（triage_results.json 的 items[].digest）
        it["digest"] = bool(DIGEST_TITLE_R.search(it["title"]))
        if dmax >= 70:
            disp = "主域" if dbest["status"] == "confirmed" else "主域(草案)"
        elif dmax >= 40:
            disp = "次域候选"
        elif dmax >= 20:
            disp = "弱相关"
        else:
            disp = "域外"
        if lit and lit.get("prim") and not domain_label_override:
            # 覆盖公式处置：题名对象直判主域，公式 D 分与原最优域降为次高域/证据
            pdom = DOM_BY_NO[lit["prim"]]
            if pdom is not dbest:
                if dbest is not None and dmax >= 20:
                    second = (dbest, dmax)
                dbest, dmax, dparts = pdom, ds[lit["prim"]], parts_by[lit["prim"]]
                domain_rule = (domain_rule + "；" if domain_rule else "") + f"文献题名对象优先→{lit['prim']}"
            disp = "主域" if dbest["status"] == "confirmed" else "主域(草案)"
        if disp not in ("主域", "主域(草案)", "次域候选"):
            incomplete_reason = ""
        # 评分卡机器层（2026-09-11 三次修订）：选卡 → 维度初判 → Gate 封顶 → TRL 加权 → 定档
        #   档位门槛：卡分 S≥80 高 / 60–79 中 / <60 低（02 簿只钉死"≥90 稀缺档"，80/60 为看板阈值待回测）；
        #   参评=处置 主域/主域(草案)/次域候选，弱相关与域外不评级；无卡类型（T15 资源体系/T25 待定）转人工不评级
        eligible = disp in ("主域", "主域(草案)", "次域候选") and not scope_ignore_reason
        s = scard = sname = None
        sdims, strl, sw, scap = [], 0, 1.0, None
        digest = eligible and is_digest(it)
        report_scope = it["title"] + "\n" + it["body"][:800]
        coarse = (not digest) and eligible and tid == "T02" \
            and REPORT_CARRIER_R.search(report_scope) and not JOURNAL_GUARD_R.search(it["title"]) \
            and not CALL_FOR_R.search(it["title"])
        if incomplete_reason:
            pass
        elif digest:
            pass
        elif coarse:
            org_txt = it["title"] + " " + it["meta"] + " " + it["body"][:600]
            if AUTH_ORG_A_R.search(org_txt):
                base_score, base_note = 45, "机构权威A档：国际权威能源机构/顶级咨询清单命中"
            elif AUTH_ORG_B_R.search(org_txt):
                base_score, base_note = 40, "机构权威B档：政府背景研究院/国家级情报体系命中"
            elif REPORT_SERIES_R.search(org_txt):
                base_score, base_note = 35, "连续报告B-档：明确为第5版以上/连续5年以上，具备时序可比性"
            else:
                base_score, base_note = 25, "机构权威C档：普通机构/行业媒体"
            coverage = 25 if disp in ("主域", "主域(草案)") else 15
            sdims = [["机构权威", base_score, 45, base_note],
                     ["领域覆盖", coverage, 25, "主域(草案) 25 / 次域候选 15"]]
            s = base_score + coverage
            scard, sname = "card_report", "报告粗档（机构权威×领域覆盖，不细评维度）"
        elif eligible and CARD_OF_TYPE.get(tid):
            raw, sdims, strl_, sw, scap = score_card(it, tid, dbest, dparts)
            strl = strl_ or 0
            if scap is not None:
                raw = min(raw, scap)
            sv = raw * sw
            if dbest is not None and dbest["no"] == "D01" \
                    and MATURE_PV_R.search(it["title"] + it["body"][:600]) \
                    and not NEW_PV_R.search(it["title"] + it["body"][:600]):
                sv = min(sv, 79)  # D01 成熟晶硅路线（用户 09-11 复核）：封顶 79 → 至多中
            s = round(sv)
            scard = CARD_OF_TYPE[tid]
            sname = CARDS[scard]["name"]
        if scope_ignore_reason:
            att = "忽略"
        elif incomplete_reason:
            att = "待定"
        elif digest:
            att = "汇总"
        elif not eligible:
            att = "域外"
        elif scard is None:
            att = "待定"
        elif coarse:
            att = "高" if s >= 65 else ("中" if s >= 50 else "低")
        elif s >= 80:
            att = "高"
        elif s >= 60:
            att = "中"
        else:
            att = "低"
        scope_reason_code, scope_reason = "", ""
        if disp == "域外" or scope_ignore_reason:
            scope_reason_code, scope_reason = scope_reason_for(
                it, dmax, dparts, lit, domain_rule, scope_ignore_reason)
        out.append({
            "date": it["date"], "src": it["src"], "meta": it["meta"], "title": it["title"],
            "url": it["url"], "doi": it["doi"], "dup": it["dup"], "ndup": 0,
            "s": s, "scard": scard, "sname": sname, "sdims": sdims,
            "strl": strl, "sw": sw, "scap": scap, "coarse": coarse,
            "dom": (dbest["no"] + " " + dbest["name"]) if dbest else domain_label_override,
            "domId": dbest["id"] if dbest else ("E99" if domain_label_override else ""),
            "domStatus": dbest["status"] if dbest else "", "d": dmax, "dparts": dparts,
            "dom2": (second[0]["no"] + " " + second[0]["name"] + "(" + str(second[1]) + ")")
                    if (second and second[0] is not None and second[1] >= 20) else "",
            "tid": tid, "type": tid + " " + tname, "t": tsc, "tband": tband, "tparts": tparts,
            "fam": fam, "card": card, "tov": tov, "talt": talt, "tconf": False,
            "disp": disp, "att": att, "lit": lit, "digest": digest,
            "scopeIgnore": bool(scope_ignore_reason), "scopeIgnoreReason": scope_ignore_reason,
            "contentIncomplete": bool(incomplete_reason), "contentIncompleteReason": incomplete_reason,
            "contentQuality": it.get("content_quality", ""),
            "domainRule": domain_rule, "bodyPrep": it.get("body_prep", ""),
            "scopeReasonCode": scope_reason_code, "scopeReason": scope_reason,
            "media_n": 0, "media_bonus": 0, "media_reports": [], "lit_merge_evidence": [],
            # 仅供本次内存合并匹配，写 JSON/HTML 前删除，避免重复存放长正文。
            "_match_text": it["title"] + "\n" + it["body"] + "\n" + it["url"],
        })

    out.sort(key=lambda x: (x["date"], x["src"], -x["d"]))

    # 文献×媒体报道新通道：DOI 全等优先；其次仅对媒体稿中明确引用的英文题名做保守匹配。
    # 不使用中文语义模糊并，避免把同领域不同论文合并。匹配证据保留到 lit_merge_evidence。
    lit_idx = [i for i, x in enumerate(out) if x["src"] == "literature"]
    media_idx = [i for i, x in enumerate(out) if x["src"] in ("news-spider", "wechat")]
    lit_dois = {}
    for i in lit_idx:
        vals = _doi_values(out[i]["doi"] + " " + out[i]["url"])
        if out[i]["doi"] and not vals:
            vals = {_norm_doi(out[i]["doi"])}
        for v in vals:
            lit_dois.setdefault(v, []).append(i)
    paper_dead = set()
    for j in media_idx:
        mx = out[j]
        candidates = []
        # ① DOI 直配：必须唯一落到一个文献条目。
        for dv in _doi_values(mx["_match_text"]):
            for i in lit_dois.get(dv, []):
                candidates.append((2.0, i, f"DOI全等:{dv}"))
        # ② 英文题名：全文直接包含，或明确引号/“题为”候选与文献题名词集 Dice≥0.80。
        if not candidates:
            quoted = QUOTE_EN_R.findall(mx["_match_text"])
            quoted += re.findall(r"(?:论文题为|题为|paper titled)\s*[:：]?\s*[“\"]?([A-Za-z][^。；\n”\"]{10,220})",
                                 mx["_match_text"], re.I)
            for i in lit_idx:
                lx = out[i]
                if lx["dom"] != mx["dom"]:
                    continue
                try:
                    dd = abs((date.fromisoformat(lx["date"]) - date.fromisoformat(mx["date"])).days)
                except ValueError:
                    dd = 99
                if dd > 5:
                    continue
                lw = _en_words(lx["title"])
                if len(lw) < 4:
                    continue
                direct = _alnum(lx["title"])
                if len(direct) >= 30 and direct in _alnum(mx["_match_text"]):
                    candidates.append((1.99, i, "英文题名规范化全文包含"))
                    continue
                for qt in quoted:
                    qw = _en_words(qt)
                    common = len(set(lw) & set(qw))
                    sim = _word_dice(lw, qw)
                    if common >= 4 and sim >= 0.80:
                        candidates.append((sim, i, f"英文题名Dice={sim:.3f},公共词={common}"))
        if not candidates:
            continue
        candidates.sort(reverse=True)
        best_score, i, evidence = candidates[0]
        # 同优先级命中多篇时不自动并，保守转人工；避免共享 DOI/栏目文本造成错并。
        tied = {c[1] for c in candidates if abs(c[0] - best_score) < 1e-9}
        if len(tied) != 1:
            continue
        lx = out[i]
        source_tier = "权威媒体" if AUTH_MEDIA_R.search(mx["meta"] + " " + mx["title"]) else "普通媒体"
        bonus = MEDIA_BONUS["authoritative" if source_tier == "权威媒体" else "normal"]
        lx["media_n"] += 1
        lx["media_reports"].append({"source": mx["meta"], "title": mx["title"], "url": mx["url"],
                                    "tier": source_tier, "bonus": bonus})
        lx["lit_merge_evidence"].append(evidence)
        lx["dup"] += 1 + mx["dup"]
        lx["media_bonus"] = min(MEDIA_BONUS_CAP, lx["media_bonus"] + bonus)
        # 媒体可见的突破/机理证据只提升对应维度，不改变文献类型/域；之后重新应用 Gate/TRL/封顶。
        media_txt = mx["_match_text"]
        media_first = bool(FIRST_R.search(media_txt) or FIRST_EN_R.search(media_txt))
        for dimrow in lx["sdims"]:
            if dimrow[0] == "指标表现×域基线" and media_first and mx["dparts"]["metric"] >= 15:
                dimrow[1], dimrow[3] = 25, "合并媒体报道含纪录/首发词+域单位：突破档"
            elif dimrow[0] == "新颖性/机理" and MECH_R.search(media_txt):
                dimrow[1], dimrow[3] = 25, "合并媒体报道含机理/重构证据"
        raw2 = sum(d[1] for d in lx["sdims"])
        if lx["scap"] is not None:
            raw2 = min(raw2, lx["scap"])
        sv2 = round(raw2 * lx["sw"]) + lx["media_bonus"]
        if lx["dom"].startswith("D01 ") and MATURE_PV_R.search(lx["_match_text"]) \
                and not NEW_PV_R.search(lx["_match_text"]):
            sv2 = min(sv2, 79)
        lx["s"] = min(100, sv2)
        # v0.97 S-G01/D-G10：媒体合并只能增强已参评论文，不能把弱相关/域外论文
        # 从“域外”改写成低分，亦不能覆盖正文不足、主体忽略或汇总免评状态。
        if (lx["disp"] in ("主域", "主域(草案)", "次域候选")
                and not lx.get("scopeIgnore") and not lx.get("contentIncomplete")
                and not lx.get("digest")):
            lx["att"] = "高" if lx["s"] >= 80 else ("中" if lx["s"] >= 60 else "低")
        else:
            lx["s"] = None
            lx["scard"] = None
            lx["sname"] = None
            lx["sdims"] = []
            lx["att"] = ("忽略" if lx.get("scopeIgnore") else
                         "待定" if lx.get("contentIncomplete") else
                         "汇总" if lx.get("digest") else "域外")
        paper_dead.add(j)
    if paper_dead:
        out = [x for k, x in enumerate(out) if k not in paper_dead]

    # 近似同事件合并（2026-09-11）：新闻/公众号源（含跨源转载）±5 天 + 同域 + 标题 bigram Dice ≥ 0.60
    #   如同一项目"中标公示/中标公告/EPC 签约"多条，保留关注档高、D 分高者为主记录。
    #   防误并：文献源不并（英文题名易撞词）；纯英文题名阈值 0.72（"X achieves N% efficiency for…"
    #   句式易撞）；双方均含数字且数字集无交集视为不同事件不并；标题先去栏目标记（｜x 取最长段）
    #   与来源尾巴（"- pv magazine"类）；去数字后完全相同的系列稿（每日速递）不并；共享 bigram < 6 不并。
    def _sim_title(s):
        s2 = max(re.split(r"[|｜]", s), key=len)
        s2 = re.sub(r"\s+[-–—]\s+[^–—]+$", "", s2)
        return re.sub(r"[\W_]+", "", s2.lower())

    def _bg(s2):
        return {s2[i:i + 2] for i in range(len(s2) - 1)} or {s2}

    def _dice(a, b):
        return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0

    _ARANK = {"高": 3, "中": 2, "低": 1, "汇总": 0.5, "待定": 0.5, "域外": 0, "忽略": 0}
    order = sorted(range(len(out)),
                   key=lambda k: (out[k]["src"], -_ARANK.get(out[k]["att"], 0), -out[k]["d"]))
    dead = set()
    for ai in range(len(order)):
        i = order[ai]
        if i in dead or out[i]["src"] not in ("news-spider", "wechat"):
            continue
        ti = _sim_title(out[i]["title"])
        bi_ = _bg(ti)
        for bj in range(ai + 1, len(order)):
            j = order[bj]
            if j in dead or out[j]["src"] not in ("news-spider", "wechat") or out[j]["dom"] != out[i]["dom"]:
                continue
            tj = _sim_title(out[j]["title"])
            if re.sub(r"\d", "", ti) == re.sub(r"\d", "", tj):
                continue
            di_, dj_ = set(re.findall(r"\d+", ti)), set(re.findall(r"\d+", tj))
            if di_ and dj_ and not (di_ & dj_):
                continue  # 双方均含数字且无共同数字 → 不同事件（英文效率纪录类易撞句式）
            bj_ = _bg(tj)
            if len(bi_ & bj_) < 6:
                continue
            try:
                dd = abs((date.fromisoformat(out[j]["date"]) - date.fromisoformat(out[i]["date"])).days)
            except ValueError:
                dd = 99
            # 纯英文题名结构相似易撞（X achieves Y% efficiency for…），阈值提高
            thr = 0.60 if (re.search(r"[一-鿿]", ti) or re.search(r"[一-鿿]", tj)) else 0.72
            if dd <= 5 and _dice(bi_, bj_) >= thr:
                out[i]["ndup"] += 1
                out[i]["dup"] += out[j]["dup"]
                if out[j]["type"].split(" ", 1)[0] != out[i]["type"].split(" ", 1)[0]:
                    out[i]["tconf"] = True  # ⑤同事件类型分歧：合并组内类型不一致，转人工
                dead.add(j)
    if dead:
        out = [x for k, x in enumerate(out) if k not in dead]

    scope_reason_summary = {}
    for x in out:
        if x["disp"] == "域外" and not x.get("scopeIgnore"):
            code = x.get("scopeReasonCode") or "O01"
            key = code + " " + OUT_SCOPE_LABELS.get(code, "未分类")
            scope_reason_summary[key] = scope_reason_summary.get(key, 0) + 1
    stats = {
        "raw": n_raw, "dedup": len(out),
        "域外": sum(1 for x in out if x["disp"] == "域外" and not x.get("scopeIgnore")),
        "主域": sum(1 for x in out if x["disp"] == "主域" and not x.get("scopeIgnore")),
        "主域草案": sum(1 for x in out if x["disp"] == "主域(草案)" and not x.get("scopeIgnore")),
        "次域候选": sum(1 for x in out if x["disp"] == "次域候选" and not x.get("scopeIgnore")),
        "高": sum(1 for x in out if x["att"] == "高"),
        "中": sum(1 for x in out if x["att"] == "中"),
        "低": sum(1 for x in out if x["att"] == "低"),
        "待定": sum(1 for x in out if x["att"] == "待定"),
        "主体忽略": sum(1 for x in out if x.get("scopeIgnore")),
        "正文不足": sum(1 for x in out if x.get("contentIncomplete")),
        "dups": sum(x["dup"] for x in out),
        "同事件合并": sum(x["ndup"] for x in out),
        "分型消歧": sum(1 for x in out if x["tov"]),
        "汇总免评": sum(1 for x in out if x["digest"]),
        "报告粗档": sum(1 for x in out if x["coarse"]),
        "软信息通道": sum(1 for x in out if x["scard"] == "card_tech" and x["tid"] in SOFTINFO_TIDS),
        "近分双候选": sum(1 for x in out if x["talt"]),
        "正文清洗": sum(1 for x in out if x.get("bodyPrep")),
        "域规则覆写": sum(1 for x in out if x.get("domainRule")),
        "同事件类型分歧": sum(1 for x in out if x["tconf"]),
        "文献×媒体报道合并": sum(x["media_n"] for x in out),
        "文献路径命中": sum(1 for x in out if x["lit"]),
        "文献域内命中": sum(1 for x in out if x["lit"] and
                          (x["lit"]["target"] not in (None, "E99") or x["lit"].get("intarget"))),
        "文献题名主域": sum(1 for x in out if x["lit"] and x["lit"].get("prim")),
    }
    for x in out:
        x.pop("_match_text", None)
    with open(os.path.join(HERE, "triage_results.json"), "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "scope_reason_summary": scope_reason_summary, "items": out},
                  f, ensure_ascii=False)
    # CSV
    with open(os.path.join(HERE, "triage_results.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["日期", "来源", "源内信息", "标题", "处置", "关注", "卡分", "技术域", "D", "次高域",
                    "主类型", "T", "评价族", "评分卡", "核心词命中", "文献分类路径", "重复", "同事件", "URL/DOI",
                    "域外原因码", "域外原因", "消歧/置信"])
        for x in out:
            lit_str = (x["lit"]["path"] + "｜命中:" + "、".join(x["lit"]["terms"])
                       + (f"｜域内叶:{x['lit']['inleaf']}" if x["lit"].get("inleaf") else "")
                       + (f"｜题名对象→{x['lit']['prim']}直判主域" if x["lit"].get("prim") else "")
                       ) if x["lit"] else ""
            conf = ";".join(filter(None, [
                x["tov"],
                "汇总·建议拆条后逐条参评" if x["digest"] else ("报告·粗档评分" if x["coarse"] else ""),
                f"低置信·次高{x['talt']['id']}({x['talt']['sc']})" if x["talt"] else "",
                "同事件类型分歧" if x["tconf"] else "",
                x.get("scopeIgnoreReason", ""), x.get("contentIncompleteReason", ""),
                x.get("bodyPrep", ""), x.get("domainRule", "")]))
            w.writerow([x["date"], x["src"], x["meta"], x["title"], x["disp"], x["att"],
                        "" if x["s"] is None else x["s"], x["dom"],
                        x["d"], x["dom2"], x["type"], x["t"], x["fam"], x["card"],
                        "、".join(x["dparts"]["core_hits"]), lit_str, x["dup"], x["ndup"],
                        x["url"] or x["doi"], x.get("scopeReasonCode", ""),
                        x.get("scopeReason", ""), conf])
    build_html(out, stats)
    print(json.dumps(stats, ensure_ascii=False))
    top = {}
    for x in out:
        if x["d"] >= 20:
            top[x["dom"]] = top.get(x["dom"], 0) + 1
    for k, v in sorted(top.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {k}: {v}")

# ---------------- 看板 ----------------
HTML_TMPL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>三库初筛看板 2026-06-15–23</title>
<style>
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 18px; font: 14px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  color: light-dark(#1a1c1f, #f0f0f0); background: light-dark(#fafafa, #17181a); }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { color: #888; font-size: 12px; margin-bottom: 14px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
.stat { padding: 10px 12px; border: 1px solid light-dark(#ddd, #333); border-radius: 10px; background: light-dark(#fff, #1e2022); }
.stat b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; }
.stat span { font-size: 12px; color: #888; }
.stat.hi { border-color: #e8963b; } .stat.hi b { color: #e8963b; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
select, input { padding: 5px 8px; border: 1px solid light-dark(#ccc, #444); border-radius: 8px;
  background: light-dark(#fff, #1e2022); color: inherit; font: inherit; min-width: 110px; }
input[type=search] { min-width: 220px; flex: 1; }
table { width: 100%; border-collapse: collapse; font-size: 13px; background: light-dark(#fff, #1e2022); }
th, td { padding: 7px 9px; border-bottom: 1px solid light-dark(#e5e5e5, #2c2e30); text-align: left; vertical-align: top; }
th { position: sticky; top: 0; background: light-dark(#f3f4f5, #242628); cursor: pointer; user-select: none; white-space: nowrap; }
tr:hover td { background: light-dark(#f6f8fa, #26282a); }
tr.sel td { background: light-dark(#eef4fb, #1e2a38); }
.badge { display: inline-block; padding: 1px 7px; border-radius: 99px; font-size: 11px; white-space: nowrap; }
.b-conf { background: #dff0e2; color: #1a7a37; } .b-draft { background: #fdebd8; color: #b05e12; }
.b-out { background: #eee; color: #888; } .b-sub { background: #eef; color: #556; }
.b-high { background: #fbdcdc; color: #b02a2a; } .b-mid { background: #fdf3d7; color: #9a7b0a; }
.b-low { background: #eee; color: #777; }
.d-num, .t-num { font-variant-numeric: tabular-nums; font-weight: 600; }
td.tl { max-width: 460px; } td.tl a { color: inherit; text-decoration: none; } td.tl a:hover { text-decoration: underline; }
#detail { margin-top: 14px; padding: 12px 14px; border: 1px solid light-dark(#ddd, #333); border-radius: 10px;
  background: light-dark(#fff, #1e2022); display: none; }
#detail h3 { margin: 0 0 6px; font-size: 15px; }
#detail .kv { display: grid; grid-template-columns: 110px 1fr; gap: 3px 10px; font-size: 13px; }
#detail .kv dt { color: #888; } #detail .kv dd { margin: 0; }
.method { margin-top: 14px; padding: 10px 14px; border-left: 4px solid #e8963b; background: light-dark(#fff8ee, #2a2419);
  font-size: 12px; color: #998; }
.count { font-size: 12px; color: #888; margin: 6px 0; }
.scope-summary { display: flex; flex-wrap: wrap; gap: 7px; margin: -4px 0 12px; }
.scope-summary .stat { min-width: 150px; padding: 7px 10px; }
.scope-summary .stat b { font-size: 17px; }
</style>
</head>
<body>
<h1>三库初筛看板 · 2026-06-15 – 06-23</h1>
<div class="sub">规则 v0.97（前置门禁 / 跨类型裁决 / 专属域优先 / 通用 Gate 与专项评分通道）· news-spider ＋ wechat-daily-news-csv ＋ literature-rss-spider · 点击表头排序，点击行看分类、评分与域外原因证据</div>
<div class="cards" id="stats"></div>
<div class="scope-summary" id="scope-summary" aria-label="域外原因汇总"></div>
<div class="filters">
  <select id="f-src"><option value="">全部来源</option></select>
  <select id="f-date"><option value="">全部日期</option></select>
  <select id="f-dom"><option value="">全部技术域</option></select>
  <select id="f-type"><option value="">全部类型</option></select>
  <select id="f-att"><option value="">全部关注</option>
    <option>高</option><option>中</option><option>低</option><option>汇总</option><option>待定</option><option>域外</option><option>忽略</option></select>
  <select id="f-disp"><option value="">全部处置</option>
    <option>主域</option><option>主域(草案)</option><option>次域候选</option><option>弱相关</option><option>域外</option></select>
  <select id="f-scope"><option value="">全部域外原因</option></select>
  <input id="f-q" type="search" placeholder="搜索标题…">
</div>
<div class="count" id="count"></div>
<div style="overflow:auto; max-height: 62vh"><table id="tbl"><thead><tr>
  <th data-k="date">日期</th><th data-k="src">来源</th><th>标题</th><th data-k="disp">处置</th>
  <th data-k="att">关注</th><th data-k="s">卡分</th><th data-k="dom">技术域</th><th data-k="d">D</th>
  <th data-k="type">主类型</th><th data-k="t">T</th><th data-k="scopeReasonCode">域外原因</th><th data-k="fam">评价族</th>
</tr></thead><tbody id="tb"></tbody></table></div>
<div id="detail"></div>
<div class="method"><b>方法说明（简化口径，非正式 RecordScore）：</b>① D = 标题词表(≤40)＋正文词表(≤30)＋主体清单(15)＋指标(15)，词表=03 域卡②（36 域，草案域已标）；指标三要素简化为"数值+域单位 15 / 数值+通用单位 7"，主体只判域清单命中（15），正文扫描前 2500 字。② T = 类型触发词(标题40/正文25)＋事件动词(建成类15/商务前期类8/拟建再降)＋数值载荷(15)＋来源先验(10)。<b>分型消歧补丁（2026-09-11 五次修订）</b>：发布+对象词动宾联判（发布+报告/皮书对象→T02；题名即《…报告》或正文前段《…报告》书名号证据→T02；产品对象仍走 T09 自然胜出）、题名招标/中标证据→T18（正文证据太泛，仅题名；题名已 T08/T18 者不覆写）、非文献源正文前段含论文证据（DOI/课题组/期刊，或题名顶刊书名号《Nature/Science…》）且题名无产业事件动词→科研先验替换产业先验且覆写→T01、T 分差&lt;10 且分≥35 双候选标<b>低置信</b>、同事件合并组类型不一致标<b>类型分歧</b>转人工。<b>S1 组增补（五次修订）</b>：T01 正文触发词证据化——非文献源正文泛词（实验/表征/样品/对比）不再单独计触发分，须论文载体证据联判（防媒体综述稿误入论文）；<b>消歧⑦</b>题名周刊/合辑类汇总稿→T25 聚合源标题流（转人工/免评候选，条目另带"汇总稿"标记）；<b>消歧⑧</b>题名会议/活动证据（研讨会/评审会/召开…）→T24；<b>消歧⑨</b>期刊论文全文转载稿（题名《刊名》文章或正文"引用本文+DOI"）→T01，压过 T02 泛触发词"展望/综述"；另对定增(T13)、政策文件特征(T19)、标准(T20)、招聘(T21)、趋势吹风/工艺解读(T23)、项目公示/吊装/可研(T08)补运行层触发词（与簿面同权）——均逐条显示在看板徽标与详情面板。③ 处置：D≥70 主域 / 40–69 次域候选 / 20–39 弱相关 / &lt;20 域外；卡分与高/中/低档为评分卡机器初判，高分≠最终档位——正式评分须走 02 八步链与打分单。④ 跨源/跨日重复按规范化标题合并；新闻/公众号源（含跨源转载）±5 天、同域、标题 bigram Dice≥0.60 的近似同事件亦合并（纯英文题名阈值 0.72；双方数字集无交集视为不同事件；仅数字不同的系列稿不并；保留关注档与 D 最高者）。⑤ <b>文献补丁</b>：文献源（标题带 <span class="badge b-sub">文</span> 标记）按《文献技术分类规则_行业图景版.docx》125 叶典型英文术语召回——术语按 叶→域 并入核心词档同阈值计分（证据词带 ※ 前缀），并独立输出叶级"文献分类路径"（可落 E99/暂不建叶，仅展示不改域归属）；<b>题名对象优先</b>：挂域叶术语命中题名时按 docx「研究对象即主分类」直判主域（公式 D 分与原最优域降为次高域/证据，仅正文命中仍按公式处置）；词表差异与口径详见同目录《文献补丁差异报告.md》。⑥ <b>评分卡机器初判（2026-09-11 三次修订，按 02 簿 12 张 family_cards 打分）</b>：<b>选卡</b>＝主类型 TYPES.card 主卡（T15 资源体系 card_resource 未建卡、T25 待定 → 无卡转人工，显示"待定"不评级）；<b>维度初判</b>＝各维度分档的机器近似——性能/规模类：数值+域单位≈达基线档、首发或纪录词+域单位≈突破档、数值+通用单位≈口径不可比档、无数值按 TRL 记 NA（TRL1-3=12 / 4-7=6 / 8-9=0）；瓶颈相关性/领域意义＝题名域核心词命中数（≥2≈CORE / 1≈SECONDARY）；主体层级＝域主体清单+一线词面；证据质量＝文献顶刊名单/DOI 20·12，新闻公众号≈单方宣称 6；<b>Gate 封顶</b>（簿面规则机器化）＝宣传性发布（无性能数值且无阶段证据）≤40、TRL8-9 无性能数值≤60、自证且无量化≤45、仅宣布工程≤45、金额未披露≤50、仅意向≤35、无数值/无基期≤30、传闻级断供≤30、征求意见稿强度封顶12、TRL8-9 常规运行通报≤30×权重；<b>TRL 加权</b>＝A/B 组卡（技术/产品/验证/生产/项目）乘 TRL 初判权重（TRL1-3=1.00 → TRL9=0.85，按 trl_framework 检测词+中文阶段动词初判、未判按 1.0），C 组商务制度类卡不乘；D01 成熟晶硅（TOPCon/PERC 且无钙钛矿叠层）封顶 79；<b>档位门槛 S≥80 高 / 60–79 中 / &lt;60 低</b>（02 簿只钉死"≥90 稀缺档须 Gate 全过"，80/60 为看板初筛展示阈值、常数待回测）；参评范围＝处置 主域/主域(草案)/次域候选，弱相关与域外不评级。<b>已知简化限制</b>：超基线幅度（×1.10/×1.20）、金额×域基线异常度、轮次与阶段匹配、一线/二线主体分级均不可机器判定，以词面档近似并逐条记录在维度档说明中——正式 RecordScore 须走 02 八步链与打分单。</div>
<div class="method"><b>⑦ 域判定修订（2026-09-11 五次修订·S6 组）：</b>正文先保守剥离明确尾部栏目/会展推广；D01 对 LED/发光器件题名且无太阳能题名证据启用负条件（路由 E99 待建光电器件域）；风/光制氢复合稿按最终产物与技术难点主体优先 D05；次高域须有题名词面或正文至少两个核心词证据，主体清单/指标/正文扩展词不能单独撑起次高域。所有覆写理由逐条显示。</div>
<div class="method"><b>⑧ 政策、标准、报告与汇总稿修订（S5 组）：</b>正式政策按发布层级、强制性、覆盖范围和填补空白评分；新发布且填补制度空白的标准不再按普通信息处理。研究报告改为机构权威×覆盖范围的粗档，不做虚假的细维度精确评分。双周刊/合辑等多事件汇总稿标记为“汇总”并暂不参评，建议拆条后逐项进入评分链。</div>
<div class="method"><b>⑨ 会议、观点与深度分析修订（S7 组）：</b>T24 会议按“影响力+实质成果发布”双判据；有影响力但无成果最多中档，评审/审查/研讨类通稿无成果封顶 40。T22/T23 按分析质量与话题监测两条通道择高，分别考察信源、结构、数据口径、话题度与科普属性；该分数表示情报价值，不冒充技术突破。</div>
<script>
const DATA = __DATA__;
const STATS = __STATS__;
let sortK = "date", sortAsc = true, selIdx = -1;
const $ = (s) => document.querySelector(s);
const el = {
  stats: $("#stats"), tb: $("#tb"), count: $("#count"), detail: $("#detail"),
  src: $("#f-src"), date: $("#f-date"), dom: $("#f-dom"), type: $("#f-type"),
  att: $("#f-att"), disp: $("#f-disp"), scope: $("#f-scope"), q: $("#f-q"),
};
const statDefs = [
  ["dedup", "去重后条目", ""], ["dups", "跨源/跨日重复", ""], ["同事件合并", "同源近似同事件", ""],
  ["主域", "主域·已确认", "hi"], ["主域草案", "主域·草案域", ""],
  ["次域候选", "次域候选(40–69)", ""], ["域外", "域外筛除(<20)", ""],
  ["高", "高关注(卡分≥80)", "hi"], ["中", "中关注(60–79)", ""], ["低", "低关注(<60)", ""],
  ["待定", "无卡·转人工", ""],
  ["主体忽略", "宁德时代主要主体·免评", ""], ["正文不足", "正文未抓全·待补抓", ""],
  ["分型消歧", "消歧覆写命中", ""], ["汇总免评", "周刊/合辑·暂不参评", ""], ["报告粗档", "报告·机构×覆盖粗档", ""], ["近分双候选", "T分差<10·低置信", ""],
  ["正文清洗", "明确尾注/推广剥离", ""], ["域规则覆写", "LED/主体优先等", "hi"],
  ["同事件类型分歧", "合并组类型不一致", ""],
  ["文献路径命中", "文献·docx 路径命中", ""], ["文献域内命中", "文献·落 D/E 域", ""],
  ["文献题名主域", "文献·题名对象直判主域", "hi"],
  ["软信息通道", "会议/观点/分析专用通道", ""],
];
el.stats.innerHTML = statDefs.map(([k, label, cls]) =>
  `<div class="stat ${cls}"><b>${STATS[k]}</b><span>${label}</span></div>`).join("");
const scopeItems = DATA.filter(x => x.disp === "域外" && !x.scopeIgnore);
const scopeCounts = scopeItems.reduce((a, x) => {
  const key = `${x.scopeReasonCode || "O01"} ${(x.scopeReason || "真实域外").split("：")[0]}`;
  a[key] = (a[key] || 0) + 1; return a;
}, {});
el.scopeSummary = $("#scope-summary");
el.scopeSummary.innerHTML = Object.entries(scopeCounts).sort((a,b) => b[1]-a[1]).map(([k,n]) =>
  `<div class="stat"><b>${n}</b><span>${esc(k)}</span></div>`).join("");
function fill(sel, vals) {
  sel.insertAdjacentHTML("beforeend", vals.map(v => `<option>${v}</option>`).join(""));
}
fill(el.src, [...new Set(DATA.map(x => x.src))].sort());
fill(el.date, [...new Set(DATA.map(x => x.date))].sort().reverse());
fill(el.dom, [...new Set(DATA.filter(x => x.dom).map(x => x.dom))].sort());
fill(el.type, [...new Set(DATA.map(x => x.type))].sort());
fill(el.scope, [...new Set(scopeItems.map(x => x.scopeReasonCode).filter(Boolean))].sort());
function attBadge(a) { return `<span class="badge ${a === "高" ? "b-high" : a === "中" ? "b-mid" : (a === "待定" || a === "汇总" || a === "忽略") ? "b-sub" : "b-low"}">${a}</span>`; }
function dispBadge(d) {
  const cls = d === "主域" ? "b-conf" : d === "主域(草案)" ? "b-draft" : d === "域外" ? "b-out" : "b-sub";
  return `<span class="badge ${cls}">${d}</span>`;
}
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function render() {
  const q = el.q.value.trim().toLowerCase();
  const list = DATA.map((x, i) => ({ ...x, i })).filter(x =>
    (!el.src.value || x.src === el.src.value) && (!el.date.value || x.date === el.date.value) &&
    (!el.dom.value || x.dom === el.dom.value) && (!el.type.value || x.type === el.type.value) &&
    (!el.att.value || x.att === el.att.value) && (!el.disp.value || x.disp === el.disp.value) &&
    (!el.scope.value || x.scopeReasonCode === el.scope.value) &&
    (!q || x.title.toLowerCase().includes(q)));
  list.sort((a, b) => {
    const va = a[sortK] ?? -1, vb = b[sortK] ?? -1;
    const c = (typeof va === "number" ? va - vb : String(va).localeCompare(String(vb), "zh"));
    return sortAsc ? c : -c;
  });
  el.count.textContent = `显示 ${list.length} / ${DATA.length} 条`;
  el.tb.innerHTML = list.map(x => `<tr data-i="${x.i}" class="${x.i === selIdx ? "sel" : ""}">
    <td class="d-num">${x.date.slice(5)}</td><td>${x.src}<div style="font-size:11px;color:#999">${esc(x.meta).slice(0, 14)}</div></td>
    <td class="tl">${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.title)}</a>` : esc(x.title)}${x.lit ? ` <span class="badge b-sub" title="文献分类路径命中">文</span>` : ""}${x.dup ? ` <span class="badge b-out">重复×${x.dup}</span>` : ""}${x.ndup ? ` <span class="badge b-out" title="同源近似同事件已合并">同事件×${x.ndup}</span>` : ""}${x.digest ? ` <span class="badge b-out" title="多事件汇总稿：建议拆条后逐项参评">汇总免评</span>` : ""}${x.scopeIgnore ? ` <span class="badge b-out" title="${esc(x.scopeIgnoreReason)}">主体免评</span>` : ""}${x.contentIncomplete ? ` <span class="badge b-draft" title="${esc(x.contentIncompleteReason)}">正文不足</span>` : ""}${x.coarse ? ` <span class="badge b-sub" title="报告采用机构权威×领域覆盖粗档评分">报告粗档</span>` : ""}${x.tconf ? ` <span class="badge b-draft" title="同事件合并组内类型不一致，转人工复核">类型分歧</span>` : ""}</td>
    <td>${dispBadge(x.disp)}</td><td>${attBadge(x.att)}</td><td class="d-num">${x.s ?? "—"}</td>
    <td>${x.dom ? esc(x.dom) : "—"}${x.dom2 ? `<div style="font-size:11px;color:#999">次: ${esc(x.dom2)}</div>` : ""}${x.domainRule ? `<div style="font-size:11px;color:#b05e12">${esc(x.domainRule)}</div>` : ""}</td>
    <td class="d-num">${x.d}</td><td>${esc(x.type)}<div style="font-size:11px;color:#999">${esc(x.tband)}${x.talt ? ` <span class="badge b-draft" title="T 最高与次高分差<10，类型存疑">低置信</span>` : ""}</div>${x.tov ? `<div style="font-size:11px;color:#b05e12">${esc(x.tov)}</div>` : ""}</td>
    <td class="t-num">${x.t}</td><td>${x.scopeReasonCode ? `<span class="badge b-out" title="${esc(x.scopeReason)}">${esc(x.scopeReasonCode)}</span>` : "—"}</td><td style="font-size:11px">${esc(x.fam)}</td></tr>`).join("");
  el.tb.querySelectorAll("tr").forEach(tr => tr.addEventListener("click", () => show(Number(tr.dataset.i))));
}
function show(i) {
  selIdx = i;
  const x = DATA[i];
  const dp = x.dparts, tp = x.tparts;
  el.detail.style.display = "block";
  el.detail.innerHTML = `<h3>${esc(x.title)}</h3><div class="kv">
    <dt>来源</dt><dd>${x.src} · ${esc(x.meta)} · ${x.date}${x.dup ? `（另有 ${x.dup} 条重复）` : ""}${x.ndup ? `（另有 ${x.ndup} 条同事件）` : ""}</dd>
    <dt>链接</dt><dd>${x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.url)}</a>` : "—"}</dd>
    <dt>处置</dt><dd>${dispBadge(x.disp)} ${attBadge(x.att)}</dd>
    ${x.scopeReasonCode ? `<dt>域外原因</dt><dd><span class="badge b-out">${esc(x.scopeReasonCode)}</span> ${esc(x.scopeReason)}</dd>` : ""}
    <dt>评分卡</dt><dd>${x.scopeIgnore ? esc(x.scopeIgnoreReason) : x.contentIncomplete ? esc(x.contentIncompleteReason) : x.digest ? "多事件汇总稿暂不参评，建议拆条后逐项评分" : x.scard ? `${esc(x.scard)} ${esc(x.sname)} · 卡分 S <b>${x.s}</b> = ${x.sdims.map(d => `${esc(d[0])} ${d[1]}/${d[2]}`).join(" ＋ ")}${x.sw < 1 ? `，× TRL${x.strl || "?"} 权重 ${x.sw}` : ""}${x.scap ? `，Gate 封顶 ≤${x.scap}` : ""} → ${attBadge(x.att)}${x.coarse ? "（报告粗档：机构权威×领域覆盖）" : "（门槛：S≥80 高 / 60–79 中 / <60 低；无卡类型待定转人工；弱相关与域外不评级）"}` : "—（无卡或未评级）"}</dd>
    ${x.scard ? `<dt>维度档说明</dt><dd>${x.sdims.map(d => `${esc(d[0])}: ${esc(d[3] || "—")}`).join("；")}${x.strl ? `<br>TRL 初判：${x.strl}${x.sw < 1 ? "（加权 " + x.sw + "）" : ""}` : "<br>TRL 未判（权重按 1.0）"}</dd>` : ""}
    <dt>D 分解</dt><dd>合计 <b>${x.d}</b> = 标题词表 ${dp.title} ＋ 正文词表 ${dp.body} ＋ 主体 ${dp.actor} ＋ 指标 ${dp.metric}${dp.metric_hit ? "（" + esc(dp.metric_hit) + "）" : ""}${dp.route ? ` ＋ 专属路线 ${dp.route}（${esc(dp.route_hit)}）` : ""}</dd>
    <dt>核心词命中</dt><dd>${dp.core_hits.length ? dp.core_hits.map(esc).join("、") : "—"}</dd>
    <dt>扩展词命中</dt><dd>${dp.ext_hits.length ? dp.ext_hits.map(esc).join("、") : "—"}</dd>
    <dt>主体命中</dt><dd>${dp.actor_hits.length ? dp.actor_hits.map(esc).join("、") : "—"}</dd>
    <dt>次高域</dt><dd>${esc(x.dom2) || "—"}</dd>
    ${x.domainRule ? `<dt>域裁决规则</dt><dd><span class="badge b-draft">覆写/排除</span> ${esc(x.domainRule)}</dd>` : ""}
    ${x.bodyPrep ? `<dt>正文预处理</dt><dd>${esc(x.bodyPrep)}</dd>` : ""}
    ${x.lit ? `<dt>文献分类路径</dt><dd>${esc(x.lit.path)} → ${x.lit.target ? esc(x.lit.target) : "暂不建（AI/通用技术，域外）"}${x.lit.target === "E99" ? "（E99 兜底叶，无域归属）" : ""}<br>英文命中：${x.lit.terms.map(esc).join("、")}（标题×${x.lit.t}·正文×${x.lit.b}）${x.lit.inleaf ? `<br>域内叶：${esc(x.lit.inpath)} → ${esc(x.lit.intarget)}` : ""}${x.lit.prim ? `<br><b>题名对象优先</b>：${esc(x.lit.prim)} 直判主域（docx：研究对象即主分类；公式 D 分与原最优域降为次高域/证据）` : ""}</dd>` : ""}
    <dt>T 分解</dt><dd>合计 <b>${x.t}</b>（${x.tband}）= 触发词 ${tp.family} ＋ 事件动词 ${tp.event} ＋ 数值载荷 ${tp.numeric} ＋ 来源先验 ${tp.prior}</dd>
    ${x.tov ? `<dt>分型消歧</dt><dd><span class="badge b-draft">覆写</span> ${esc(x.tov)}——题名营销词让位于更强证据（方法说明②）</dd>` : ""}
    ${x.talt ? `<dt>近分候选</dt><dd><span class="badge b-draft">低置信</span> 次高候选 ${esc(x.talt.id)} ${esc(x.talt.name)}（T=${x.talt.sc}，与最高分差&lt;10，不强行 argmax，建议人工复核）</dd>` : ""}
    ${x.tconf ? `<dt>类型分歧</dt><dd><span class="badge b-draft">转人工</span> 同事件合并组内类型不一致——合并保留关注档/D 高者，类型需人工裁决</dd>` : ""}
    <dt>评价族 / 卡</dt><dd>${esc(x.fam)} → ${esc(x.card) || "—"}</dd>
  </div>`;
  render();
}
document.querySelectorAll("th[data-k]").forEach(th => th.addEventListener("click", () => {
  const k = th.dataset.k;
  sortAsc = sortK === k ? !sortAsc : true;
  sortK = k;
  render();
}));
[el.src, el.date, el.dom, el.type, el.att, el.disp, el.scope].forEach(s => s.addEventListener("change", render));
el.q.addEventListener("input", render);
render();
</script>
</body>
</html>
"""

def build_html(items, stats):
    def js(x):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    doc = HTML_TMPL.replace("__DATA__", js(items)).replace("__STATS__", js(stats))
    path = os.path.join(HERE, "三库初筛看板_20260615-23.html")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)
    print(path, f"({os.path.getsize(path):,} B)")


if __name__ == "__main__":
    main()

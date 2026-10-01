# AI_INTERFACE —— triage_engine 机器调用契约（v1.11）

本文档面向**AI 程序/Agent/服务端调用方**：给出能力边界、端到端流程、输入/输出 JSON Schema、
字段字典与全部评价机制表（未删减）。人类可读入门见 [README.md](README.md)。

机制表与参考文档原件（自包含快照，随版本同步）在 [docs/](docs/)：01 类型评判表 / 02 评分框架机制表
（含 v1.03–v1.08 历轮档位政策页）/ 03 域参数库 / 两份基准 docx（文献技术分类、新闻类型语义分类——
LLM 语义准绳的编辑源）。运行层不读 docx/xlsx：docx 的依次分类路由摘要已固化为 `rules/lit_rules_data.ROUTING_DIGEST`，
表格口径已代码化进 `rules/*.py` 与管线——以代码为准，docs/ 供 AI 与人核对语义。

---

## 1. 能力一句话

输入三库行记录（新闻爬虫/微信公众号/文献 RSS），输出每条记录的：**技术领域判定 + 新闻类型判定 +
新闻价值评分（S1–S8）+ 优先级层（S9）+ 档位政策结果（S10）+ 直评口径（v1.11：入域直接 高/中/低，域外不评分）+
事件级去重合并**，并生成 JSON/CSV/域外分析/HTML 看板四件套。规则层纯标准库、确定性、可离线。

## 2. 端到端流程

```
rows[]（行记录）
  │  ① 读取层预处理（io_rows / 调用方自备）：body 清洗、content_quality 分层
  ▼
完全同题去重（规范化题名 or url）
  │  ② 分类轨（语义裁决，不计算 D/T 分）
  ▼
领域判定（D/E 参数域 → 语义叶 GT/AI → 扩展域 → 域外）        ── 每条留 rule/reason/terms/snippet 证据
类型判定（T01–T25，载体身份与必要条件优先，题名主事件锚定）
  │  [可选] ③ LLM 语义判定合并（run_llm 产出 decisions，覆盖域/类型，规则层留痕）
  ▼
B1 媒体投资解读改判（v1.08，评分前）：T19 × 规划话题 × 解读框架（出炉/定调/释放信号/投资方向）
  × 无政策本体锚点（《》文件名×发布/印发族 或 国家级主体词）→ 改判 T23（直接按机制出档）
  │  ④ 评分轨
评分卡维度评分（S4 Σ，类型专属卡/专项通道）
TRL 加权（S5，仅 TRL 加权卡） → Gate 封顶（S6） → 记录合成（S7） → 档位（S8：≥75高 ≥55中 <55低）
S9 优先级分层（U_type 档位上限 + P0/P1/P2 排序层）
S10 档位政策（地板/硬上限/上限/论文统一档位）——只改档位与层，不改分数（S-V02 信源分除外）
  ▼
直评口径（v1.11）：不设 参考/待定/忽略 类目——入域（domainDisp≠域外）attention=scoreBand=高/中/低
                    （T02 走 S-R01 粗分档、T25 经通用技术卡兜底、范围忽略 ignored 仅审计字段）；
                    域外不评分（scoreBand=未评分、attention=域外）。v1.07 参考区分区停用（section 恒主榜）。
                     → 【v1.09 展示链路】按最终类型映射 展示大类（论文/新闻）/展示小类/归入大类（A/B/C/D）三字段（纯展示，不进评分）
  │  ⑤ 事件级去重（union-find）：C-R01 DOI / C-R03 文号名·题名相似
  ▼
排序（分区 → 日期 → 层 → -分值 → 关注 → 标题）→ 四件套写盘（out_dir）→ validate 结构断言
```

## 3. 输入契约

### 3.1 行记录 schema（`rows[i]`）

| 键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `src` | string | ✅ | 三选一：`news-spider` / `wechat` / `literature`（影响载体判定与去重通道） |
| `date` | string | ✅ | ISO 日期 `YYYY-MM-DD` |
| `title` | string | ✅ | 标题（分类的第一证据位；题名锚定规则以此为准） |
| `body` | string | △ | 正文（可为空串；空正文走 T25/域外 兜底） |
| `url` | string | 建议 | 原文链接；LLM 决策按 url 匹配；去重键之一 |
| `meta` | string | 建议 | 来源内信息（账号名/媒体名/期刊名）；信源提示分 S-V02 与证据层级判据 |
| `doi` | string | literature 建议 | 论文 DOI；C-R01 去重键 |
| `body_prep` | string | 可选 | 预处理审计（io_rows 读取器自动生成） |
| `content_quality` | string | 建议 | `full`/`abstract`/`preview`/`digest`/`empty`；低质量触发 S-G01 封顶 |

读取器（`triage_engine.io_rows`）：`read_news_csv / read_wechat_csv / read_literature_csv / read_batch_dir / read_rows_json`，
列名契约见 AI 程序无需关心时可只用 `read_batch_dir`（目录含 `news-spider/articles-*.csv`、`wechat/*.csv`、`literature/news_with_abstract_*.csv`）。

### 3.2 LLM 决策 schema（`llm_decisions`，可选）

`{"version", "model", "judged", "accepted", "skipped_low_conf", "decisions": {url: {...}}}`；
每条决策：`{domain_path, domain_no, type_id, terms[], alternatives[], reason, confidence(high|medium|low), ruleLayerRef, isProblemCase}`。
`domain_path="域外"` 且 `domain_no=""` → 改判域外；`type_id` 须在 T01–T25。合并原则：LLM 覆盖规则层域/类型，规则层结果保留为参考痕迹（`llmJudged=true`）。

## 4. 输出契约

### 4.1 `run()` 返回值 / `semantic_results.json`

```json
{
  "method": "…+doi-carrier-premise-v110+direct-banding-v111",
  "stats": { "raw", "records", "duplicates", "eventMerged", "mainDomain", "semanticOnly",
             "outOfScope", "typePending", "high", "medium", "low", "refZone", "manual", "unscored",
             "p0", "p1", "p2", "s10Floored", "s10Capped", "bandCapped", "sourceHinted", "llmJudged",
             "displayChain", "paperSubtypes", ... },
  "outsideSummary": { "total", "reasons[]", "types[]", "topics[]", "sources[]" },
  "items": [ /* 字段字典见 §4.2 */ ]
}
```

注意：v1.11 直评口径——`high/medium/low` 覆盖**全部入域记录**（无 参考/待定/忽略 类目；`refZone`/`manual` 恒 0 保留为审计位）；`high+medium+low+outOfScope == records` 闭合。

### 4.2 item 字段字典（全量）

| 字段 | 含义 |
|---|---|
| `date/src/meta/title/url/doi/duplicates` | 输入回显；`duplicates`=完全同题并入数 |
| `domain` | 领域标签（如 `D01 光伏`、`AI93 算力能源基础设施`、`LLM …`） |
| `domainId` | 领域 id（`semantic_branch_ai`=AI00 待细分） |
| `domainDisp` | 处置：`主域`/`主域(草案)`/`主域(语义域)`/`主域(扩展)`/`域外` |
| `domainConfidence` | `明确`/`可判`/`未满足必要条件` |
| `domainRule` / `domainReason` / `domainTerms` / `domainSnippet` | 领域裁决规则号/理由/证据词/摘句 |
| `secondaryDomains[]` | 附加参考域（≤3） |
| `type` / `typeId` | 类型标签（`T01`–`T25`，见 §5.2） |
| `typeRule` / `typeReason` / `typeEvidence` / `typeAlternatives[]` / `typeConfidence` | 类型裁决链 |
| `family` / `card` / `cardName` | 类型族 / 所用评分卡 |
| `priorityTier` | S9 排序层：`P0`/`P1`/`P2`（域外为空串） |
| `section` | **v1.11 恒 `主榜`**（v1.07 参考区分区停用，字段保留兼容 schema） |
| `bandUnderlying` | **v1.11**：恒等于 `scoreBand`（v1.07 参考区底层档语义停用，字段保留兼容 schema） |
| `displayCategory` | **v1.09**：展示大类——论文（T01）/新闻（T02–T24）/待定（T25）；域外记录为 `—` | 
| `displaySubcategory` | **v1.09**：展示小类——论文=四分型**逐条判定**（综述/研究型/分析类/新闻·评论·观点；题名综述词→综述，评估/情景/技术经济词→分析类，非文献源（媒体解读/转载报道，全文转载特征除外）→新闻·评论·观点，默认研究型）；新闻=知识资产/工程与产业化/企业经营合作与资本/资源市场与产业链/政策法规与标准/人才与组织动态/观点与交流；域外=`域外` |
| `displayClass` | **v1.09**：归入大类 A科研知识/B产业化主链(链2-5)/C企业支撑/D外部环境（依据《新闻类型展示分类.xlsx》与 02 机制表《大类与产业链导航》）；纯展示不影响 S1–S10 |
| `llmJudged` | 是否被 LLM 语义判定覆盖 |
| `value` / `valueDisplay` | S8 分值（T02 报告为区间串如 `35–54`，value=null） |
| `attention` | **v1.11 直评**：`高`/`中`/`低`（入域）或 `域外`（未入域，不评分） |
| `scoreBand` | 档位：`高`/`中`/`低`（入域）或 `未评分`（域外） |
| `scoreStatus` | `已评分`/`区间评分`（T02 粗分档）/`未进入评分`（仅域外） |
| `scoreRaw` / `scoreAfterGate` / `cap` / `weight` | S4 原始Σ / S6 后 / 封顶值 / TRL 权重 |
| `dimensions[]` | 评分卡维度明细 `[名称, 得分, 满分, 注记]` |
| `route` / `routeTrlBand` / `routeTrlBasis` / `trl` | S3 技术路线与 TRL 带 |
| `evidenceLevel` | `E1` 官方原始 / `E2` 权威机构 / `E3` 单一媒体（S-G04 判据） |
| `gateActions[]` | 全部 Gate/政策动作留痕（U_type/S10 地板上限/S-V02/S-G0x/C-R03…） |
| `missingEvidence[]` | 缺失证据清单 |
| `scoreAudit[]` | S1–S8+S9+S10+C-R03 审计链 `[步骤, 名称, 说明]` |
| `ignored` / `ignoredReason` | 范围免评审计位（宁德时代主体规则等；v1.11 起仅留痕，不再拦截评分与输出） |
| `bodyPrep` / `contentQuality` | 预处理审计 / 正文质量 |
| `outsideReason` / `outsideReasonDetail` / `outsideTopic` | 域外结构化原因（O1–O9）与主题 |
| `mergedRefs[]` | 事件级并入记录 provenance（title/src/meta/url/date/band/value） |

## 5. 评价机制总表（核心内容，未删减）

### 5.1 领域体系（分类轨上半）

- **D/E 参数域**（行业图景已登记、有评分参数库）：D01 光伏 / D02 锂电池 / D03 储能系统 / D05 氢基能源 /
  D06 风电 / D07 核电含聚变 / D08 压缩空气储能 / D09 钢铁脱碳 / D10 水泥 / D11 燃烧掺氨氢 /
  D12 CCUS / E01 光热 / E04 燃料电池 / E10 超级电容 / E26 地热 …（含域族完整清单见 `rules/`）
- **语义叶 GT/AI**（文献技术语义树，`target=None/E99` 表示评分参数未映射但**不是域外**）：
  AI85 文本模型 … AI93 算力能源基础设施 … GT116–GT125 材料族等
- **扩展域**：GT125 石化化工节能降碳 / GT126 气候风险与基础设施韧性 / GT127 数字软件与信息安全 / GT128 光电与发光器件
- **判定层级**（从严到宽）：专属路线 → 标题主对象 → 首段主对象 → 正文证据链（题名/首段全零的深部枚举=侧带提及，不入域）。
  歧义词（battery/储能/氢/钙钛矿/低碳/脱碳 等）需第二域内要素消歧；机构名误中防护（"中科院半导体研究所"）。
- **域外**：通读标题正文后无任何登记对象 → 必须给出 O1–O9 结构化原因。

### 5.2 类型体系 T01–T25（分类轨下半，载体身份优先）

T01 论文文献 ｜ T02 研究报告 ｜ T03 专利 ｜ T04 软著等权利 ｜ T05 科研项目 ｜ T06 检测认证 ｜
T07 工程验证 ｜ T08 项目工程 ｜ T09 产品装备 ｜ T10 运行数据 ｜ T11 企业经营 ｜ T12 合作 ｜
T13 融资 ｜ T14 并购 ｜ T15 资源矿产 ｜ T16 市场供需 ｜ T17 供应链 ｜ T18 招投标 ｜ T19 政策法规 ｜
T20 标准认证 ｜ T21 人才与组织 ｜ T22 观点访谈 ｜ T23 深度分析评论 ｜ T24 会议活动 ｜ T25 待定

裁决原则：载体形态优先（文献 RSS→T01、直播/会议预告→T24、N 部门部署→T19）；必要条件＋排除条件；
**题名主事件锚定**（正文尾部栏目/推广杂质不决定主类型）；跨类型证据优先级 precedence 兜底。

### 5.3 评分轨 S1–S8

| 步骤 | 名称 | 机制 |
|---|---|---|
| S1 | 技术领域 | 严格语义裁决结果（不计算 D 分） |
| S2 | 新闻类型 | 严格语义裁决结果（不计算 T 分） |
| S3 | 路线TRL | 只按技术路线前沿定 TRL 带与权重 w（题名命中路线优先；无路线取域带中位数；扩展域中性 TRL5） |
| S3b | 评分卡兜底 | 无专属卡的类型用通用技术知识卡 |
| S4 | 维度Σ | 类型专属卡逐维计分（合作/人才 T12/T21、技术投入品 T09、报告 T02 见专项通道） |
| S5 | TRL 加权 | 仅 TRL 加权卡乘 w；C 组卡不乘 |
| S6 | Gate | 封顶：S-G01 仅标题证据54/74、S-G03 宣传性主张54、S-G04 E3 高结论74（纪录/里程碑/首证豁免见 §5.4） |
| S7 | 记录合成 | 单一主事件计分，附加背景不抬分 |
| S8 | 最终档位 | `≥75 高；≥55 中；<55 低` |

专项通道：**T12 合作**（普通合作封顶54）、**T21 招聘**（普通招聘封顶54）、**T09 技术投入品**（具名材料产品四维）、
**T02 报告 S-R01**（方法×样本×连续性×信源 → 高75–89/中55–74/低35–54 区间，不伪造精确点分）。

### 5.4 S9 优先级分层 + S10 档位政策（v1.04 + v1.06；v1.07 参考区 v1.11 起停用）

S9：`最终档位 = min(S8 档位, U_type)`；U_type：T11/T13/T14/T24 → 中。排序层 P0 技术优先 / P1 产业制度 / P2 软信息后置。

S10（顺序：硬上限 → 地板 → 常规上限 → 论文统一档位；v1.08 新增 S-A04/S-A05 硬上限与 B1 类型改判；v1.07 参考区分区 v1.11 起停用）：

| 类别 | 规则 | 触发条件（摘要） | 结果 |
|---|---|---|---|
| 硬上限 | S-A01 汽车白名单未中 | 整车/车型/试驾语境且非（固态/钠电/新型电池装车/光伏器件/直接CCUS/车网结合/智驾升阶） | 上限=低 |
| 硬上限 | S-A02 生物医药无爆点 | 生物医药域且无克隆/脑机接口等爆点 | 上限=低 |
| 硬上限 | S-A03 非聚焦领域 | 电池/能源/零碳脱碳/AI/半导体/芯片 之外（具身/机器人属聚焦） | 上限=低 |
| 硬上限 | S10-D 地方申报 | 省级地名＋申报/入库/指标配置且非国家级主体（市级规划防护） | 上限=低 |
| 硬上限 | **S-A04 常规发电项目汇总稿（v1.08 W3）** | T08/T10 × 题名 多个/多项/一批/批量/陆续/汇总 × 并网/投产/投运/开工/发电 × 新能源/光伏/风电/水电/电站，且题名无低TRL新型发电技术词（钙钛矿/量子点/有机光伏/叠层/海上漂浮式/单机大容量风机等，词表草案） | 上限=低 |
| 硬上限 | **S-A05 未来态计划（v1.08 W1/W2）** | 题名 预计/将/拟/计划/有望（≤14字窗口）× 投运/商业运营/并网/建成/交付/量产，或 将在/将部署/拟部署；首座×示范在建（first_project）豁免保 S-P05b 中 | 上限=低 |
| 无地板类 | no_floor_soft | T11/T13/T14/T24、招投标公告无技术参数 | 内容地板不豁免 |
| 地板 | S-B01 瓶颈事实 | 聚焦域×题名锚定瓶颈词×程度/量化证据 | 高·P0 |
| 地板 | S-F01 首创认证 | 『首个/首创＋认证/标准/投产/投运/商业运营』（**限技术事件类 T06–T10**，v1.09 窄修——正文 boilerplate 背景句不抬 T12 合作/T16 市场等软类型；排除基金会议语境、在建态与 v1.08 未来态） | 高·P0 |
| 地板 | S-F02 工程里程碑 | 聚焦域×T08/T10×题名里程碑（倒送电/并网成功/全流程贯通/商业运营，v1.08 排除将来时）×百兆瓦级 | 高·P0 |
| 地板 | S-P02 国家重点规划 | 题名十五五/部委部署/国家重点研发＋**政策本体锚点**（v1.08 B1：《》文件名×发布/印发族或国家级主体词；媒体出炉/定调/信号稿不触发） | 高·P0 |
| 地板 | S-P01(v2) 顶刊正刊 | 聚焦域×T01/T05×Nature/Science **正刊**（子刊/大子刊排除；±16字符载体语境守卫） | 高·P0 |
| 地板 | S-P03 聚焦域政策 | T19 政策与战略 | 中·P1 |
| 地板 | S-P06 科研转载/解读 | T22/T23×科研载体证据（或专业编辑信源×科研解读题名） | 中·P1 |
| 地板 | S-P07 实质技术案例/风险 | 题名案例/风险词×量化证据 | 中·P1 |
| 地板 | S-P08 首部标准 | T20×首发/新制定 | 中·P1 |
| 地板 | S-P04 一般技术类 | 聚焦域×技术事件型（T01/T03/T04/T05/T06/T07/T09，非计划态） | 中 |
| 地板 | S-P05 产业化落地 | 聚焦域×T08/T10 落地事实（含首座×商业化/示范在建 S-P05b） | 中 |
| 上限 | S10-B 软信息 | 投融资/并购/市场/会议/宣传/观点/招聘无技术瓶颈载荷 | 低 |
| 上限 | S10-C 常规动态 | 无技术细节建厂/招标/立项/资源法规常规；高TRL(≥9)常规运行无跃迁 | 低 |
| 论文 | S-P01v2/S-P09/S-P10 | paper_class=T01 或 T22/T23×科研转载：正刊→高；题名突破词×量化参数→最低中；**其余统一中** | 中（默认） |
| 类型改判 | **B1 媒体投资解读（v1.08）** | T19 × 规划话题 × 解读框架（出炉/定调/释放信号/投资方向/总投资将超/探析 v1.09 补词）× 无政策本体锚点 → 改判 T23（typeRule=C-T08/T19-媒体解读改判（B1），审计留痕） | T23 直接按机制出档 |
| 前提 | **C-T16 载体前提（v1.10，DOI×语义共决）** | 前提① `src=literature` 一律 T01；前提② wechat/news 的 DOI（字段/链接/正文）只是引用线索——**有 DOI ≠ 论文**：论文本体载体（《刊名》文章/全文转载/学术速递/网络首发/引用本文）或题名期刊锚定＋学术命题才可 T01（正文级 DOI 不再单独构成载体）；DOI 迹象×题名媒体分析/报道框架（解读/评述/盘点/梳理/综述：/科普/评论/观点/Top N/据报道/科学家发现/Scientists discover/study shows 等）×学术命题×非本体载体 → 改判 T23（typeRule=`C-G05/C-T16-DOI载体前提`，DOI 记入证据链）；证据级 E1 收窄为 literature 源，wechat/news 带 DOI → E2『报道引用论文 DOI（二手可溯源）』 | T01 收紧 / 假文献→T23 直评三档 |
| 输出 | **直评口径（v1.11）** | 不设 参考/待定/忽略 类目：入域记录 attention=scoreBand=高/中/低（T02 走 S-R01 粗分档：scoreStatus=区间评分、value=null、valueDisplay=区间串；T25 经通用技术知识卡 card_tech 兜底三档；范围忽略 `ignored`/`ignoredReason` 降为审计字段不再拦截）；域外不评分（scoreBand=未评分、attention=域外）；v1.07 参考区分区停用（section 恒主榜、bandUnderlying=scoreBand） | 主输出即全集，恒四件套 |
| 展示 | **展示链路（v1.09）** | 按最终类型映射 `DISPLAY_CHAIN_MAP`：T01→论文·四分型**逐条判定**（综述/研究型/分析类/新闻·评论·观点，`_paper_display_subtype` 题名证据级联）·A；T02–T06→新闻·知识资产·A（T05 计分走 B链3）；T07–T10→工程与产业化·B(链2-5)；T11–T14→企业经营合作资本·C；T15–T18→资源市场产业链·C/D/B链6；T19/T20→政策法规标准·D；T21→人才组织·C；T22–T24→观点与交流·A；T25→待定；域外→`—/域外/—`。stats 增 `displayChain`＋`paperSubtypes` 计数。**不参与任何评分/档位/优先级**（用户 2026-09-24 口径） | 主榜（v1.11 恒主榜） |

### 5.5 LLM 语义判定层（可选第三轨）

- 协议：Anthropic Messages（`POST {LLM_BASE_URL}/v1/messages`），模型默认 glm-5.2，max_tokens 建议 4000，temperature 0。
- Prompt：两份基准 docx 语义（领域树菜单＋类型菜单＋docx v2 依次分类路由摘要 ROUTING_DIGEST 注入）。
- **预置叶冻结（v1.09，决策版本 2026-09-24-v3）**：除非与零碳产业/AI与智能科技/通用技术完全无关（判域外），新闻与文献的 `domain_path` 必须逐字取自预置菜单（含"运行扩展域"），无完全匹配时选语义最近的预置叶并在 reason 说明；禁止自拟"扩展:"新路径与新增节点（暂时冻结，用户 2026-09-24 口径）。`type_id` 仍须为 T01–T25。
- **载体前提（v1.10，决策版本 2026-09-24-v3.1）**：约束 3 增补——`src=literature` 一律 T01；wechat/news 中出现 DOI（字段/链接/正文）只是引用线索，**有 DOI ≠ 论文**：仅当主对象是论文本体（全文转载、学术速递、以论文题名为题、正文即摘要/研究内容）才判 T01；报道/解读/分析/评论某论文（附 DOI）按主事件分型（多为 T23 深度分析），不得因有 DOI 判 T01（与规则层 C-T16 同口径）。
- 范围：默认全量（`--all`）；采纳策略：confidence=high 或规则层未决（域外/T25/AI00 停根）。
- 断点续跑：`llm_semantic_audit.jsonl`（每批一条，i 索引去重）；429 退避 30/60/120/240s。
- 输出合并：见 §3.2；低置信跳过计 `skipped_low_conf`。

### 5.6 事件级去重（v1.05/v1.06b，管线末端）

| 通道 | 匹配键 | 守卫 |
|---|---|---|
| C-R01 论文 | 标准化 DOI 精确匹配（跨源） | T01、非域外 |
| C-R03 新闻·文号名 | 题名《》文号/文件名（规范后 ≥8 字符；排除『《刊名》+文章/独家/目录』载体模式） | 日期窗 ≤2 天；**不要求同域** |
| C-R03 新闻·题名相似 | 规范化题名 bigram Jaccard ≥0.75 | 同域＋日期窗 ≤2 天；系列文（上）/（下）分节标记不同不并簇 |

主记录 = 正文质量(full>abstract>preview>digest) → 证据层级(E1>E2>E3) → 正文最长 → 更早发布；
并入记录进 `mergedRefs`，评分只保留主记录一次。域外/T25（域外侧）不参与；v1.11 起范围忽略仅审计、不再影响参与。

### 5.7 常数草案（null 待回测惯例）

| 常数 | 当前值 | 状态 |
|---|---|---|
| S-V02 专业编辑信源加分 | +5（REAI Lab、国际能源小数据等，只加分不联动档位） | 草案 |
| C-R03 题名 Jaccard 阈值 | 0.75 | 草案 |
| C-R03 日期窗 | 2 天 | 草案 |
| 《》文号名最短规范长度 | 8 字符 | 草案 |
| 尾注清洗阈值 | 300 字（S6_DISABLE_STRIP=1 可 A/B） | 草案 |
| FUTURE_LANDED 将来时窗口 | 预计/将/拟 后 ≤14 字内落 投运/商业运营/并网 等 | 草案 |
| NOVEL_GEN_R 低TRL发电技术词表 | 钙钛矿/量子点/有机光伏/叠层/海上漂浮式/单机大容量风机等（S-A04 豁免用） | 草案 |

## 6. 错误处理与运行语义

- 入参校验：`rows` 非空、每条 dict、`src/date/title` 非空、`src` ∈ 三源；违规抛 `ValueError`（信息含行号）。
- 模块名占用：宿主进程已 import 其他路径的同名管线模块 → `RuntimeError`（解决：子进程运行引擎）。
- 结构断言（validate，内建）：记录数一致、裁决字段齐全、域外三段原因、
  **v1.11 直评契约**（attention ∈ {高,中,低,域外}；入域 attention==scoreBand ∈ {高,中,低}；
  域外 value 空且 attention=域外；high+medium+low+outOfScope==records；refZone==manual==0）、
  四件套落盘非空。断言失败=输出损坏，不应消费。
- 幂等：`run()` 每次全量重算并覆盖 out_dir 四件套；`llm` 层凭 audit JSONL 断点续跑。
- 确定性：规则层无随机源；LLM 层 temperature=0 但仍建议以 audit/decisions 文件为准做缓存。
- 性能量级：单进程约 2–3k 行/分钟（规则层）；LLM 层 `--batch 16 --sleep 6` 约 500 条/40 分钟（视限流）。

## 7. 版本策略

完整修订流水线（改哪、怎么验证、怎么同步、怎么发布）见 [MAINTENANCE.md](MAINTENANCE.md)；本节为要点。

- 版本号在 `triage_engine.__version__` / `ENGINE_VERSION`；输出 JSON `method` 串尾部为机制标签（当前 `direct-banding-v111`）。
- 升级机制时：更新 `pipeline/` + `rules/` 快照、`ENGINE_VERSION`、README/AI_INTERFACE 版本表，
  并同步 `docs/` 下的机制表快照（02 评分框架表用开发仓 patch_workbooks 系列脚本增补后拷贝）
  与 `docs/requirements_ledger.txt`（与开发仓 `问题.txt` 同步）。
- 判定口径以 `问题.txt`（requirements_ledger）历轮累计要求为最高基准，不回退旧口径。

## 8. 调用示例

```python
# ① 最小调用（规则层）
from triage_engine import run
result = run(rows, "out/dir")

# ② 三源 CSV 批次
from triage_engine import run
from triage_engine.io_rows import read_batch_dir
rows, _ = read_batch_dir("batch/2026-06-26")
result = run(rows, "out/dir")

# ③ 全流程（规则层 → LLM → 合并）
from triage_engine import run
from triage_engine.llm import run_llm
from triage_engine.io_rows import read_batch_dir
rows, _ = read_batch_dir("batch/2026-06-26")
run_llm(rows, "out/dir", batch=16, sleep=6)                     # .env 提供 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL
result = run(rows, "out/dir", llm_decisions="out/dir/llm_semantic_decisions.json")

# ④ 服务化（每请求子进程隔离）
import subprocess, json
p = subprocess.run([sys.executable, "-m", "triage_engine.cli", "run",
                    "--rows", "req_rows.json", "--out", "req_out"],
                   capture_output=True, text=True, encoding="utf-8")
result = json.load(open("req_out/semantic_results.json", encoding="utf-8"))
```

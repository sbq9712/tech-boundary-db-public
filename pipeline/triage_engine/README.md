# triage_engine —— 能源/零碳/AI 情报三库分类评分引擎（v1.11）

把"三库原始数据 → 领域/类型分类 → 新闻价值评分 → 档位政策 → 事件级去重 → 直评口径 → 看板四件套"
的完整机制封装为**一个可调用的函数包**：传入行记录列表，返回结构化结果并落盘四件套。
规则层**零第三方依赖**（纯 Python 标准库，Python ≥ 3.10），可直接放服务器 / 其他设备 / GitHub。

- 机器可读契约（面向 AI 程序/Agent）：见 **[AI_INTERFACE.md](AI_INTERFACE.md)**
- 历轮口径全量台账：`docs/requirements_ledger.txt`（问题.txt 快照）
- 逐条修复原因文档：`outputs/triage-review-*/修复报告_v1.0*.md`（开发仓内）

## 版本

**v1.11**（2026-09-25）＝ v1.04 分类规则 ＋ v1.05 事件级去重 ＋ v1.06(b) 论文统一档位 ＋ v1.08 未来态/汇总稿/媒体解读守卫 ＋ v1.09 展示链路与 LLM 预置叶冻结 ＋ v1.10 载体前提（C-T16：DOI×语义共决，有 DOI ≠ 论文） ＋ v1.11 **直评口径**（不设 参考/待定/忽略 类目：入域直接 高/中/低，域外不评分；v1.07 参考区停用）。
method 串：`…+doi-carrier-premise-v110+direct-banding-v111`（写入每个输出 JSON 的 `method` 字段，可据此判别版本）。

## 安装

无需 pip 安装——把 `triage_engine/` 目录整体复制进项目，或本仓库根目录直接使用：

```bash
python -m triage_engine.cli version   # 验证：triage_engine v1.11 method=…direct-banding-v111
```

依赖：仅标准库（`requirements.txt` 为说明性文件）。LLM 层同样用标准库 `urllib`。

## 快速开始

### Python API（推荐）

```python
from triage_engine import run
from triage_engine.io_rows import read_batch_dir   # 三源 CSV 读取器（可选）

rows, _files = read_batch_dir("你的三源CSV目录")             # 或自行构造 rows（schema 见下）
result = run(rows, "outputs/my_out")                # 纯规则层
# result = run(rows, "outputs/my_out", llm_decisions="path/to/llm_semantic_decisions.json")  # 合并 LLM 判定

print(result["stats"])        # 高/中/低/refZone/P0/P1/P2…
for x in result["items"]:     # 每条记录的完整判定+评分+审计
    print(x["date"], x["title"][:30], x["domain"], x["typeId"], x["scoreBand"], x["section"])
```

`rows` 是行记录字典列表（必填 `src/date/title`，`body` 可空串；建议补 `url/meta/doi/body_prep/content_quality`），
完整 schema 与字段字典见 AI_INTERFACE.md §2–§3。

### 命令行

```bash
python -m triage_engine.cli run --batch-dir 你的三源CSV目录 --out OUT                # 批次目录（三源扁平布局）
python -m triage_engine.cli run --news a.csv --wechat b.csv --literature c.csv --out OUT
python -m triage_engine.cli run --rows rows.json --out OUT --llm-decisions dec.json
python -m triage_engine.cli llm  --batch-dir ... --out OUT --batch 16 --sleep 6     # LLM 语义判定（需 .env）
```

### 可选 LLM 语义判定层

```python
from triage_engine.llm import run_llm
dec = run_llm(rows, "outputs/my_out", batch=16, sleep=6)          # 需要 .env（LLM_BASE_URL/LLM_API_KEY/LLM_MODEL）
result = run(rows, "outputs/my_out", llm_decisions="outputs/my_out/llm_semantic_decisions.json")
```

glm-5.2 / Anthropic Messages 协议；断点续跑（audit JSONL）；429 长退避。默认只采纳
confidence=high 或规则层未决（域外/T25/AI00 停根）的判定。见 AI_INTERFACE.md §5.5。

## 输出（写入 out_dir 四件套）

| 文件 | 内容 |
|---|---|
| `semantic_results.json` | 完整结果：`method/stats/outsideSummary/items[]`（`run()` 的返回值同源） |
| `semantic_results.csv` | 全字段表格（含 分区 列） |
| `域外内容分析_20260615-23.csv` | 域外记录的原因分组/主题分析 |
| `三库严格语义分类看板_20260615-23.html` | 自包含看板：统计卡、主榜表（v1.11 直评：无参考区表，入域全部三档）、详情审计链 |

## 目录

```
triage_engine/
├── README.md            # 本文件（人类读者）
├── AI_INTERFACE.md      # 机器契约（AI 程序读者）：流程图/Schema/字段字典/机制表
├── MAINTENANCE.md       # 修订流程：发现问题→改单源→验证链→同步包→发布升级
├── requirements.txt     # 依赖说明（纯标准库）
├── .env.example         # LLM 层环境变量样例
├── engine.py            # run() 规则层入口（函数式封装）
├── llm.py               # run_llm() LLM 语义判定入口
├── io_rows.py           # 三源 CSV 读取器（news-spider/wechat/literature）
├── cli.py               # 命令行入口（python -m triage_engine.cli）
├── pipeline/            # 管线模块（与 outputs 运行层 v1.08 同源快照，仅路径适配）
│   ├── build_github_triage.py           # 基础层：读取/预处理/评分卡/域参数
│   ├── build_strict_semantic_triage.py  # 语义分类+评分+档位政策+直评口径+去重+看板
│   └── run_llm_semantic_triage.py       # LLM 语义判定 runner
├── rules/               # 规则单源（与 outputs/classification-scoring-rules-20260909 同源快照）
│   ├── cls_data.py / expand_domains_data.py / lit_rules_data.py / score_data.py
│   └── trl_scoring_data.json            # TRL 加权参数库
├── docs/                                # 机制文档自包含（快照，随版本同步）
│   ├── 00_严格语义分类与评分执行说明.md   # 执行总说明（v1.11 直评口径；§5 = 演进索引）
│   ├── 01_新闻类型分类评判表.xlsx        # T01–T25 类型评判机制表
│   ├── 02_技术领域×新闻类型评分规则表.xlsx # S1–S10 评分框架机制表（含 v1.03–v1.08 历轮档位政策页；大类与产业链导航＝v1.09 展示链路）
│   ├── 03_技术领域参数库.xlsx            # 38 域参数库
│   ├── 新闻类型展示分类.xlsx             # v1.09 展示链路源表（论文四分型＋新闻小类＋归入大类 A/B/C/D）
│   ├── 文献技术分类规则_行业图景版.docx   # LLM 语义判定基准①：领域树（编辑源）
│   ├── 新闻类型语义分类规则_行业图景版.docx # LLM 语义判定基准②：类型菜单（编辑源）
│   └── requirements_ledger.txt          # 历轮用户口径台账（问题.txt 快照）
└── tests/test_smoke.py                  # 合成数据冒烟测试（v1.07–v1.11 机制断言）
```

## 测试

```bash
PYTHONIOENCODING=utf-8 python -m triage_engine.tests.test_smoke      # 直接跑
PYTHONIOENCODING=utf-8 python -m pytest triage_engine/tests -q       # 或 pytest
```

冒烟测试覆盖：v1.11 直评口径（不设 参考/待定/忽略 类目：T02 报告直接 S-R01 粗分档出高、T23 深度分析直接按机制出低、域外不评分、范围忽略仅审计字段 ignored）、
v1.10 载体前提（literature 一律 T01；wechat/news 的 DOI×题名媒体框架 → T23，全文转载载体 rescue → T01）、
v1.09 展示链路（论文/新闻两级＋归入大类 A/B/C/D，域外标域外，计数闭合）、
v1.09 论文四分型逐条判定（研究型默认）与 S-F01 窄修（T12 合作稿正文 boilerplate 不抬档）、
v1.07 #1（AI 模型发布题名锚定 T09→中，不被正文会议词误入 T24）、
v1.08 W1（『预计10月转入商业运营』未来态 → S-A05 硬上限低·P2）、
v1.08 W3（『多个新能源项目并网』常规发电汇总稿 → S-A04 硬上限低·P2）、
v1.08 B1（十五五媒体投资解读稿 → T19 改判 T23 直接按机制出档）、T01 论文主榜、
域外结构化原因、宁德时代主体范围免评（ignored 仅审计留痕）。

端到端实数据验证（开发仓内部记录，该数据目录未随包分发）：`cli run --batch-dir …/2660624-260630`
（2818 行 → 2281 条，事件级合并 16；v1.11 直评口径下原参考区/忽略记录全部并入三档，与 outputs 运行层同源结果）。

## 并发/嵌入注意

引擎以全局模块名 `build_github_triage` / `build_strict_semantic_triage` 加载管线；
同一进程内请勿与开发仓 `outputs/github-triage-20260615-23/` 下的同名模块混用
（引擎检测到占用会显式报错）。服务化部署时每个请求在子进程中运行 `run()` 即可完全隔离。

## 版本历史（摘要）

| 版本 | 日期 | 要点 |
|---|---|---|
| v1.02 | 2026-09-18 | LLM 语义判定合并 + S9 优先级分层（P0/P1/P2） |
| v1.03 | 2026-09-19 | S10 档位政策（地板/上限）；E26 地热；聚焦域族 |
| v1.04 | 2026-09-20 | M1–M12：瓶颈题名锚定、招投标低、首创防护、里程碑高地板、地方申报硬上限等 |
| v1.05 | 2026-09-22 | 事件级去重 C-R01/C-R03（DOI/文号名/题名 Jaccard） |
| v1.06(b) | 2026-09-22 | 论文统一档位 S-P01v2（正刊收窄）/S-P09/S-P10；载体语境守卫；系列文防误并 |
| v1.07 | 2026-09-23 | AI 模型发布题名锚定补词；参考区（T02/T23 分区展示；**v1.11 起停用**）；打包为 triage_engine |
| v1.08 | 2026-09-23 | **S-A05** 未来态计划硬上限（预计/将/拟×投运·部署 → 低）；**S-A04** 常规发电项目汇总稿硬上限（多个×并网，题名点名低TRL新技术除外）；**S-P02 政策本体锚点**＋**B1** 十五五媒体投资解读稿改判 T23（当时入参考区，v1.11 起直接按机制出档） |
| v1.09 | 2026-09-24 | **展示链路**：输出 展示大类（论文/新闻）/展示小类/归入大类（A/B/C/D）三字段＋看板展示列＋stats.displayChain（纯展示不影响评分，依据《新闻类型展示分类.xlsx》）；**论文四分型逐条判定**（综述/研究型/分析类/新闻·评论·观点，题名证据级联＋`paperSubtypes` 计数）；**S-F01 首证地板限技术事件类 T06–T10**（正文 boilerplate『首个+认证』不再抬 T12 合作/T16 市场等软类型，生产 7 条 高→低/中）；**B1 补词"探析"**；**LLM 提示词 v3 预置叶冻结**——除非完全无关判域外，否则必须归入预置叶子节点/预置类型，禁止自拟"扩展:"新路径（run_llm 层，决策版本 2026-09-24-v3） |
| v1.10 | 2026-09-24 | **C-T16 载体前提（DOI×语义共决）**：literature 库一律 T01；wechat/news 的 DOI（字段/链接/正文）只是引用线索——**有 DOI ≠ 论文**：论文本体载体（《刊名》文章/全文转载/学术速递/网络首发）或题名期刊锚定＋学术命题才可 T01；DOI×题名媒体分析/报道框架（解读/盘点/综述：/Scientists discover/study shows 等）→ 改判 T23 深度分析（审计留痕 `C-G05/C-T16-DOI载体前提`，DOI 记入证据链）；正文级 DOI 不再单独构成 T01 载体；证据级 E1 收窄为 literature 源（wechat/news 带 DOI → E2 二手可溯源）；**LLM 提示词 v3.1 载体前提**（决策版本 2026-09-24-v3.1）。实战：06-27『本周学术文章Top10』T01·中→T23·参考；06-25《储能科学与技术》全文转载 T25→T01·中·P0 |
| v1.11 | 2026-09-25 | **直评口径**：不设 参考/待定/忽略 类目——入域记录直接按机制链给出 高/中/低（T02 走 S-R01 粗分档、T25 经通用技术卡 card_tech 兜底、范围忽略 ignored 降为审计字段）；域外不评分（scoreBand=未评分、attention=域外）；v1.07 参考区分区停用（section 恒主榜）；输出恒四件套（无《移出记录》第五件套）。实战：主批 2421 条全部闭合（高 56/中 1246/低 914/域外 205），三测试批重建原三档零漂移 |

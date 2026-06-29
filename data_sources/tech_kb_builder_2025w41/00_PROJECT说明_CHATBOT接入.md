# tech-knowledgebase-builder 项目说明与 chatbot 接入指南

本文档用于帮助 chatbot 或接入方理解 `tech-knowledgebase-builder` 项目的知识库底座、文件结构、检索顺序、质量边界和参数回答规则。

本文件夹是一个完整的 chatbot 接入包，包含项目说明文档和需要接入 chatbot 的知识库文件副本。

## 1. 项目定位

`tech-knowledgebase-builder` 不是 chatbot 应用本体，而是一个本地优先的技术知识库生产线。

它负责：

- 读取本地文件和已下载数据
- 规范化来源记录
- 生成分类、抽取、参数索引和知识库导出
- 绑定 `source_id`、`unit_id`、`evidence_text`
- 生成 RAG 切片、source index、evidence map、domain index 和参数索引
- 通过质量门禁决定哪些内容可以进入正式输出

chatbot 负责：

- 理解用户问题
- 根据领域和问题类型选择检索路径
- 查询 RAG、参数索引、source index 和 evidence map
- 组织自然语言回答
- 明确说明证据边界、不确定性和知识库未覆盖内容

chatbot 不应自行搜索网页，不应调用外部资料补答案，不应根据模型记忆或行业常识补写参数最优值。

## 2. 本接入包目录结构

```text
chatbot_integration_package/
├── 00_PROJECT说明_CHATBOT接入.md
├── export_manifest.json
├── knowledge_base/
│   ├── knowledge_base.md
│   └── knowledge_base_compact.md
├── chatbot_context/
│   ├── system_context.md
│   ├── domain_router.md
│   ├── answer_guidelines.md
│   └── retrieval_policy.md
├── rag/
│   ├── kb_chunks.jsonl
│   └── kb_metadata.json
├── indexes/
│   ├── domain_index.json
│   ├── entity_index.json
│   ├── evidence_map.json
│   ├── source_index.jsonl
│   ├── source_index.sqlite
│   ├── parameter_values.jsonl
│   ├── journal_parameter_values.jsonl
│   ├── news_parameter_values.jsonl
│   ├── wechat_parameter_values.jsonl
│   ├── parameter_index_summary.json
│   ├── optimal_parameter_index.json
│   └── optimal_parameter_index.sqlite
├── quality_reports/
│   ├── quality_gate_report.json
│   ├── quality_gate_report.md
│   ├── fact_grounding_report.json
│   ├── fact_grounding_report.md
│   ├── export_allowed_ids.json
│   └── export_blocked_ids.json
└── config_snapshot/
    ├── taxonomy.yaml
    ├── parameter_rules.yaml
    ├── quality_rules.yaml
    └── export_config.yaml
```

## 3. 当前知识库状态

当前底座由上一轮已下载/已处理的本地数据重新整合生成。

统计信息：

| 项目 | 数量 |
|---|---:|
| source records | 31,265 |
| knowledge units / claims | 31,265 |
| parameter values | 59,333 |
| journal parameter values | 47,701 |
| news / industry parameter values | 10,800 |
| WeChat parameter values | 832 |
| optimal parameters | 0 |
| domains | 8 |
| RAG chunks | 32 |
| blocked items | 0 |

`optimal parameters = 0` 是刻意保守的结果。当前参数值主要来自 baseline 数字抽取，缺少明确测试条件、统一口径、可比组和 explicit best 证据，因此不能直接生成“最优值”结论。

## 4. chatbot 推荐加载顺序

建议 chatbot 启动或接入时按以下顺序理解本包：

1. 读取本说明文档。
2. 读取 `chatbot_context/system_context.md`。
3. 读取 `chatbot_context/retrieval_policy.md`。
4. 读取 `chatbot_context/answer_guidelines.md`。
5. 读取 `knowledge_base/knowledge_base_compact.md`。
6. 读取 `indexes/domain_index.json` 作为领域路由表。
7. 读取 `indexes/parameter_index_summary.json` 作为参数覆盖情况摘要。
8. 将 `rag/kb_chunks.jsonl` 导入向量库或关键词检索库。
9. 将 `indexes/*.jsonl` 和 `indexes/*.sqlite` 挂载为精确查询索引。

## 5. 不同问题类型的检索策略

### 5.1 概览类问题

用户问：

- 这个知识库包含哪些领域？
- 某领域大概有什么内容？
- 当前知识库覆盖范围是什么？

优先读取：

1. `knowledge_base/knowledge_base_compact.md`
2. `knowledge_base/knowledge_base.md`
3. `indexes/domain_index.json`
4. `rag/kb_chunks.jsonl`

### 5.2 具体依据类问题

用户问：

- 这个结论依据是什么？
- 哪个来源支持这个说法？
- source_id 对应原文是什么？

优先读取：

1. `indexes/evidence_map.json`
2. `indexes/source_index.sqlite`
3. `indexes/source_index.jsonl`

回答时应尽量给出 `source_id`、`unit_id` 或 `evidence_text`。

### 5.3 参数类问题

用户问：

- 某参数是多少？
- 最高效率是多少？
- 最低成本是多少？
- 最优值是多少？
- 新闻报道中的项目参数是多少？
- 论文实验值和产业披露值是否一致？

优先读取：

1. `indexes/parameter_index_summary.json`
2. `indexes/optimal_parameter_index.json`
3. `indexes/optimal_parameter_index.sqlite`
4. `indexes/parameter_values.jsonl`
5. `indexes/journal_parameter_values.jsonl`
6. `indexes/news_parameter_values.jsonl`
7. `indexes/wechat_parameter_values.jsonl`
8. `indexes/evidence_map.json`
9. `indexes/source_index.sqlite`

## 6. 参数来源类型规则

参数索引按证据来源拆分为三类：

| 类型 | 字段值 | 文件 | 用途 |
|---|---|---|---|
| 期刊/论文/科研证据 | `journal_evidence` | `journal_parameter_values.jsonl` | 技术性能、实验结果、模型结果、研究边界 |
| 新闻/产业报道证据 | `news_evidence` | `news_parameter_values.jsonl` | 项目进展、企业披露、产能、成本、商业化阶段 |
| 公众号观点或整理 | `wechat_opinion` | `wechat_parameter_values.jsonl` | 观点、背景、二次整理、线索 |

默认禁止行为：

- 不得把期刊参数和新闻参数混成同一个排行榜。
- 不得把新闻/产业报道值说成论文实验最优值。
- 不得把论文实验值说成产业项目已达到值。
- 不得把公众号整理值说成客观最优值。
- 没有 explicit best 或 comparable group 时，不得回答“最优值为……”

推荐表达：

> 当前知识库中，论文证据下报告的参数值包括……；新闻/产业报道中披露的项目参数包括……。两者来源类型、测试条件或口径不同，不能直接比较或排序。

## 7. 为什么当前不能直接回答“最优值”

当前参数值大多是从已有 `KnowledgeUnit.key_numbers` 中保守转换得到。

这些数字满足：

- 出现在本地输入中
- 可以回查到 `source_id` 或 `evidence_text`
- 可作为 reported value 保存

但多数不满足：

- 测试条件明确
- 对象类型一致
- 单位和口径一致
- 同一 comparable group
- 来源明确声称 best/highest/lowest/record

因此当前 `optimal_parameter_index.json` 中不会生成真正的 `journal_best_records` 排名结论。news 和 wechat 的值也只能作为报道值或线索展示。

## 8. RAG 与精确索引的职责分工

`rag/kb_chunks.jsonl` 用于语义检索、路由和上下文召回。

它不应该承担完整参数数据库职责。

参数和来源的精确查询应使用：

- `indexes/parameter_values.jsonl`
- `indexes/journal_parameter_values.jsonl`
- `indexes/news_parameter_values.jsonl`
- `indexes/wechat_parameter_values.jsonl`
- `indexes/optimal_parameter_index.sqlite`
- `indexes/source_index.sqlite`
- `indexes/evidence_map.json`

也就是说：

- RAG 负责“找到可能相关的方向”
- SQLite/JSONL 索引负责“查准具体数值、来源、证据”

## 9. 质量边界

当前质量门禁：

- `quality_gate_report.json`
- `quality_gate_report.md`

当前质量状态为 pass，blocked items 为 0。

事实依据机械检查：

- `fact_grounding_report.json`
- `fact_grounding_report.md`

需要注意：fact grounding warnings 很多，主要原因是 baseline 数字抽取较粗，会把标题编号、年份、化学式数字等也作为 reported values。chatbot 不应把这些 warning 参数直接当成高质量关键参数或最优值。

## 10. chatbot 回答原则

chatbot 应遵守：

1. 只使用本包中的知识库文件和挂载索引。
2. 不自动搜索网页。
3. 不根据模型记忆补充知识库没有的信息。
4. 不根据行业常识补写参数典型值。
5. 涉及数字、日期、公司、论文、项目、政策、商业化阶段时，必须回查来源。
6. 新闻证据不能直接当作技术验证结论。
7. 公众号观点不能写成客观事实。
8. 单条来源不能泛化为行业趋势。
9. 输入未说明时，应回答“当前知识库未说明”。
10. 参数不可比时，应明确说明不可比原因。

## 11. 建议的后端接入方式

建议工程接入方式：

```text
chatbot
  -> 读取 system_context / retrieval_policy / answer_guidelines
  -> RAG 检索 kb_chunks.jsonl
  -> domain_index.json 做领域路由
  -> parameter_index_summary.json 判断参数覆盖
  -> SQLite / JSONL 精确查询参数和来源
  -> evidence_map.json 回查证据
  -> source_index.sqlite 回查来源记录
  -> 组织回答并说明质量边界
```

如果只做轻量接入，可以先使用：

- `knowledge_base_compact.md`
- `retrieval_policy.md`
- `domain_index.json`
- `parameter_index_summary.json`
- `kb_chunks.jsonl`

如果要回答精确参数问题，必须接入：

- `parameter_values.jsonl`
- `journal_parameter_values.jsonl`
- `news_parameter_values.jsonl`
- `wechat_parameter_values.jsonl`
- `optimal_parameter_index.sqlite`
- `evidence_map.json`
- `source_index.sqlite`

## 12. 后续优化建议

当前底座已经可以接入 chatbot，但如果要提升回答质量，建议后续继续做：

1. 运行 Codex 参数抽取任务，语义过滤真正关键参数。
2. 对参数值进行人工或 Codex source_type 审查。
3. 给可比参数建立 `comparable_group_id`。
4. 生成正式 `metric_cards`，并按 journal/news/wechat 分区。
5. 对高价值领域生成 domain/problem/route/status cards。
6. 将 SQLite 查询封装为 chatbot 工具函数。


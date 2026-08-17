# 技术知识库总览

> 质量边界说明：本知识库仅基于项目输入文件和已通过质量审查的本地内容整理，不包含自动网页搜索结果，不使用外部资料补全。所有关键结论原则上应能回溯到 source_id、KnowledgeUnit 或 evidence_text。若某项信息在输入中缺失，应标注“输入内容未说明”或“当前输入未找到，需人工核对”。
> 证据类型说明：文献证据可用于说明技术原理、方法、性能数据和机制；新闻证据可用于说明企业、项目、政策和产业事件；公众号内容主要作为观点、背景解释或线索，不应作为客观技术结论的唯一依据。

> generated_at: 2026-06-25T11:29:52.293894+00:00

## 0. 使用说明与质量边界

本知识库是面向前沿技术 chatbot 的底层知识库，不是 chatbot 应用本体。正式内容仅来自已通过质量门禁的本地输入和 Codex 审查结果。

## 1. 领域导航

- 领域卡目录：`outputs/domain_cards/`
- domain index：`outputs/indexes/domain_index.json`

## 2. 当前发展现状导航

- 现状卡目录：`outputs/status_cards/`

## 3. 关键问题与瓶颈导航

- 问题卡目录：`outputs/problem_cards/`

## 4. 技术路线导航

- 路线卡目录：`outputs/route_cards/`

## 5. 关键指标导航

- 指标卡目录：`outputs/metric_cards/`
- 参数值索引：`outputs/indexes/parameter_values.jsonl`
- 分来源参数索引：`outputs/indexes/journal_parameter_values.jsonl`、`outputs/indexes/news_parameter_values.jsonl`、`outputs/indexes/wechat_parameter_values.jsonl`
- 最优参数索引：`outputs/indexes/optimal_parameter_index.json`

## 6. 各领域知识卡导航

- 领域知识卡目录：`outputs/domain_cards/`

## 7. 回答策略

- 发展阶段问题优先读现状卡和领域卡。
- 瓶颈问题优先读问题卡和路线卡。
- 技术路线问题优先读路线卡、现状卡和 evidence map。
- 指标问题优先读指标卡和 evidence map。
- 依据问题优先读 evidence map 和 source index。

## 8. 原文与证据回查

- RAG chunks：`outputs/rag/kb_chunks.jsonl`
- evidence map：`outputs/indexes/evidence_map.json`
- parameter index：`outputs/indexes/optimal_parameter_index.json`、`outputs/indexes/parameter_values.jsonl` 以及 journal/news/wechat 分来源参数索引
- source index：`outputs/indexes/source_index.sqlite` 或 `outputs/indexes/source_index.jsonl`

## 9. 质量门禁
- gate_status: pass
- approved_items: 31265
- blocked_items: 0

## 10. Records 统计
- records: 31265

## 11. 领域分布
- 产业降碳: 52
- 光伏: 1635
- 关键矿产与资源: 29
- 其他: 13432
- 其他储能: 752
- 智能科技: 12718
- 清洁能源: 286
- 电池: 2361

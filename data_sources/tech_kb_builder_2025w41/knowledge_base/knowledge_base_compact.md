# 技术知识库紧凑版

> 质量边界说明：本知识库仅基于项目输入文件和已通过质量审查的本地内容整理，不包含自动网页搜索结果，不使用外部资料补全。所有关键结论原则上应能回溯到 source_id、KnowledgeUnit 或 evidence_text。若某项信息在输入中缺失，应标注“输入内容未说明”或“当前输入未找到，需人工核对”。
> 证据类型说明：文献证据可用于说明技术原理、方法、性能数据和机制；新闻证据可用于说明企业、项目、政策和产业事件；公众号内容主要作为观点、背景解释或线索，不应作为客观技术结论的唯一依据。

> generated_at: 2026-06-25T11:29:52.295739+00:00

本文件用于 chatbot 快速加载全局边界、问题类型路由和已通过质量门禁的高层结构。
- gate_status: pass
- records: 31265

## 1. 领域速览
- 使用 `outputs/indexes/domain_index.json` 定位领域和子领域。

## 2. 问题类型路由
- 发展现状：优先 `status_cards/`。
- 关键瓶颈：优先 `problem_cards/`。
- 技术路线：优先 `route_cards/`。
- 指标口径：优先 `metric_cards/`。
- 参数最优值：优先 `optimal_parameter_index.json`；没有可比依据时不得强行排名。
- 参数来源类型：论文、新闻/产业报道、公众号参数值默认不得混合排序。
- 综合背景：使用 `domain_cards/`。

## 3. 不同问题优先读取哪些卡片
- 问发展状况：`status_cards/` + `domain_cards/`。
- 问瓶颈在哪里：`problem_cards/` + `route_cards/`。
- 问路线是否可行或是否商业化：`route_cards/` + `status_cards/` + `evidence_map.json`。
- 问指标或性能：`metric_cards/` + `evidence_map.json`。
- 问最佳/最高/最低参数值：`optimal_parameter_index.json` + `parameter_values.jsonl` + `evidence_map.json`。
- 同时存在论文值和新闻值时：并列说明来源类型和可比性限制，不得直接排序。
- 问依据是什么：`evidence_map.json` + `source_index.*`。

## 4. 回答时必须区分的证据类型
- 文献证据、新闻证据、公众号观点或整理必须分开表述。

## 5. 需要回查原文的情况
- 涉及数字、日期、公司、论文、政策、产品、商业化阶段或来源引用时回查 `source_id`。

## 6. 禁止回答方式
- 不得编造知识库未说明的信息。
- 不得把公告或规划写成投运或商业化。
- 不得把单条来源泛化为行业趋势。

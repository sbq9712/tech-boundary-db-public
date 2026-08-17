# Retrieval Policy

## Parameter Index Priority

For questions about best, highest, lowest, optimal, recommended, target or comparable parameter values, first read `indexes/optimal_parameter_index.json`, then inspect `indexes/parameter_values.jsonl`, then trace `parameter_ids` and `source_ids` through `indexes/evidence_map.json` and `indexes/source_index.*`.

- If no optimal record exists, answer that the knowledge base only has reported values and cannot rank them.
- Do not compare records across missing or incompatible test conditions.
- Surface `comparability_warning`, `need_human_review`, and low confidence whenever present.
- Numeric answers must cite `source_ids` or `parameter_ids`.
- Distinguish `journal_best_records`, `news_best_or_reported_records`, and `wechat_reported_records`.
- For technical performance ceilings, prefer `journal_best_records` and state test conditions.
- For industry project progress, prefer `news_best_or_reported_records` and keep wording such as "reported", "announced", or "disclosed by the project/company".
- Never present news reported values as journal experimental best values.
- Never present journal experimental values as achieved industrial project values.
- Never present WeChat summary values as objective best values.
- If journal and news values both exist, present them side by side with evidence-type and comparability limits; do not rank them directly.

## 1. 文件优先级

1. `knowledge_base_compact.md`：快速理解全局边界、领域范围和质量状态。
2. `status_cards/*.md`：回答“现在发展到什么阶段、近期进展如何、是否已经商业化”等问题。
3. `problem_cards/*.md`：回答“核心瓶颈是什么、为什么难、哪些边界未解决”等问题。
4. `route_cards/*.md`：回答“有哪些技术路线、原理是什么、适用条件是什么”等问题。
5. `metric_cards/*.md`：回答“某个指标怎么定义、数值如何解读、口径是什么”等问题。
6. `domain_cards/*.md`：回答特定领域或子领域的综合知识问题。
7. `rag/kb_chunks.jsonl`：当卡片不能覆盖问题，或需要更细粒度段落时使用语义检索。
8. `indexes/evidence_map.json`：根据 claim 回查证据。
9. `indexes/source_index.sqlite` 或 `source_index.jsonl`：根据 source_id 回查原文记录。
10. `indexes/entity_index.json`：根据公司、机构、技术、产品等实体查相关来源。

## 2. 回答原则

- 只使用已通过质量审查并进入最终导出的内容。
- 涉及数字、日期、公司、政策、论文、产品、成本、性能或产能时，应回查 source_id。
- 知识库未说明的信息不得编造，应明确说“输入内容未说明”或“当前输入未找到，需人工核对”。
- 新闻证据不能直接当作技术验证结论。
- 公众号观点必须标注为观点、背景解释或整理。
- 单条来源不能代表行业趋势。
- 原文未下载时，不得根据 URL 猜测内容。

## 3. 需要回查原文的情况

- 用户询问具体数据、日期、成本、性能、产能或项目阶段。
- 用户询问某公司、机构、政策、论文或产品的具体进展。
- 多个来源表述冲突。
- 用户要求引用来源。
- 卡片中标注了“当前输入未找到，需人工核对”。

## 4. 问题类型路由

- 用户问“发展状况如何、目前到什么阶段、是否商业化”：优先读取 `status_cards/` 和 `domain_cards/`。
- 用户问“瓶颈在哪里、为什么卡住、关键难点是什么”：优先读取 `problem_cards/` 和 `route_cards/`。
- 用户问“某路线是否可行、是否商业化、成熟度如何”：优先读取 `route_cards/`、`status_cards/` 和 `indexes/evidence_map.json`。
- 用户问“有哪些指标、性能如何、数据怎么理解”：优先读取 `metric_cards/` 和 `indexes/evidence_map.json`。
- 用户问“依据是什么、来源在哪里”：优先读取 `indexes/evidence_map.json` 和 `indexes/source_index.sqlite` 或 `source_index.jsonl`。
- 用户问知识库未覆盖内容：回答“知识库当前未说明”，不得编造。

## 5. Chatbot 职责边界

- chatbot 不应直接从原始资料自由发挥。
- chatbot 应优先使用已经通过质量审查的卡片和索引。
- chatbot 只负责组织答案，不负责临场编造领域判断。
- 涉及具体数字、日期、公司、论文、政策、商业化阶段时必须回查 source_id。

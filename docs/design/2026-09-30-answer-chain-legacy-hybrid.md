# 五.1/五.2/五.3 答案侧 legacy_hybrid 真实核验链落地与调查结论（2026-09-30）

## 范围与授权边界

不修改 tech-db（只读源），不修改引擎上游，不写入 EDMUNDSdaONE；
镜像回滚链：`techdb-canonical-qa:0930d → 0930e → … → 0930h`（逐版保留）。

## 一、移植（五.1）

旧答案侧链路（tech-db/qa-backend，docker-compose QA_PIPELINE_PROFILE=legacy_hybrid
的启用面）逐模块移植为两份孪生：

- 链 A（canonical-qa 直连）：`services/canonical-qa/qa-backend/answer_chain.py`
  + 同目录 11 个核验模块（epistemic/verifier/claim_mapping/citation_grounding/
  numeric_facts/primary_evidence/answer_status/knowledge_boundary/answer_repair/
  provenance/evidence_metadata）。
- 链 B（门户 agent_service）：`backend/app/services/qa_verification/` 同一逻辑
  的包内副本（仅 import 行差异 + llm_compat 桥读 agent_service 的 AI 配置），
  `stream_agent_response` 生成前注入认识论分类与提示词，生成后跑
  `run_answer_verification`，改写经 SSE `replace` 事件回写。

链路顺序与旧系统一致：classify（生成前）→ epistemic 提示词 → 生成 →
fail-safe verify → claim mapping → numeric facts → grounding →
bounded repair（qualified/delete/remap）→ recheck → AnswerStateMachine 四态
（SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / UNVERIFIED）→
knowledge_boundary 校准弃权 → 泄密面扫描。失败一律 FAIL_SAFE 降级，
绝不阻断答案流；`verification NOT_RUN → UNVERIFIED`（fail-closed）。

原 `_claim_check`（编号/带引用句比例启发式）仅保留为链不可用时的
degraded 兜底分支，不再作为主核验。

## 二、状态语义修复（五.2）

- 拒答识别 `detect_refusal`：`_REFUSAL_RE`（库-source + 没有/未找到…）∧
  `_REFUSAL_TAIL_RE`（情报/信息/相关…）双命中且 ≤120 字。
  「量子恐龙税制」回归：修复前 verified + sufficient 误报；修复后
  纯拒答 → UNSUPPORTED + 「库内边界 ≠ 现实不存在」文案（契约测试覆盖）。
- 2026-09-30 复测（0930h）：量子恐龙税制回答为「拒答头 + 相关线索清单」
  混合形态（569 字），正确地走四态评估 → PARTIALLY_SUPPORTED +
  `unsupported_claims_remain`，边界消息列「可以确认」项。已知边界：
  混合形态不在纯拒答阈值内，与旧系统行为一致。

## 三、「钠离子电池储能应用现状」调查（五.3）

现象：旧链路有实质回答；新链路曾称"无实质资料"/全 claim UNSUPPORTED。

根因（三轮实测定案，均非召回问题）：

1. **分类面错配**：新部署检索编排 FINAL_TOP_K=25（旧 ≈6），生成前
   epistemic 分类只盖 top-5 → verifier 的有效 chunk 集是 1-5，
   把 [24]/[25] 引用判为「不对应任何已有chunk（1-5）」、全部 chunk
   claims 为空 → 全部核心主张 fail-closed UNSUPPORTED。
   实测证据：/tmp/qa_sodium3.jsonl（UNVERIFIED verification_not_run →
   UNSUPPORTED all_core_claims_unsupported，grounding valid=25）。
2. **GLM-5.2 推理预算**：verifier 单次 LLM 60s 超时 ×3（sodium6）或
   `max_tokens=4096` 被推理耗尽 → content 空 → empty_response ×3
   （sodium8）。旧系统同型号问题只出现在 classify（其注释自证：
   "GLM-5.2 reasoning: low caps leave content empty"，故 classify 已是
   8192）——verifier 在旧系统没炸是因为 glm-5.3-flash 快且非长推理。
3. **claim mapping 外层截断**：mapping 内层 2 组负载 ×2 次 ×8192 token
   超 160s 外层预算（sodium7）→ claims 空、coverage_gate FAIL 0.0。

不是原因：召回/截断/重排/过滤/图扩展——三轮 grounding valid=25、
evidence status sufficient、检索 23-25 条候选；与「引用预算差异」无关。

修复（0930e→0930h，两份孪生同步）：

- 分类面：生成前首轮 top-5（旧对齐），空输出升级 25→10；verify 侧
  `classify_full_coverage` ×5 批面（旧单次分类面大小）补齐
  already..len(citations)，chunk_id 平移，单批 FAIL_SAFE 丢弃。
- verifier：`max_tokens` 4096→8192（循旧系统 classify 先例），
  内层单次 `QA_VERIFY_TIMEOUT=90`（compose 注入），外层编排预算
  `QA_VERIFY_BUDGET=300`（独立 env 名，避免与 verifier 内层同名冲突）。
- mapping：外层 `QA_MAPPING_TIMEOUT` 160→300。
- repair：QUALIFY_PREFIX 重复守卫（已带前缀的句子按 weaken 记账，
  不再叠加「（据现有证据尚未证实）×3」）。

修复后实测（同一问题三连发，模型 glm-5.2，语料 68523+295）：

| 运行 | verification | 终态 | 说明 |
|------|-------------|------|------|
| sodium7 | PASSED | SUPPORTED / evidence_sufficient | 全链首次贯通 |
| sodium8 | empty_response ×3 → UNVERIFIED | UNVERIFIED / technical_failure:verifier | fail-closed，不误报 |
| sodium9 | FAILED → 修复 qualify×4（无叠加）→ recheck FAILED | UNSUPPORTED / all_core_claims_unsupported + 校准弃权 | replace 事件回写 |

三种终态都是状态机的诚实输出；run-to-run 波动来自 GLM-5.2 推理型
输出的固有方差，不是链路逻辑。链 B（门户）同题复测：UNSUPPORTED +
qualify×4 + 校准边界 + SSE replace（/tmp/qa_sodium_portal2.jsonl）。

## 四、验收与回滚

- 契约测试 24 项（backend/tests/test_qa_verification_chain.py，api 容器内
  通过）：拒答语义、四态状态机、数值降级、grounding、边界文案、
  epistemic 注入、端到端 stub-LLM 四路径、compact 载荷、分类面阶梯、
  批面补齐与 chunk_id 平移、QUALIFY 去重守卫。
- 全库 231 passed / 3 failed（均为环境性预存失败：模型目录需上游
  /models、docling 测试按宿主布局解析路径；与本次改动无关）。
- 镜像回滚：`TECHDB_IMAGE_TAG=0930d docker compose up -d canonical-qa`
  （每版镜像都保留）；api 侧为 docker-cp 热补（镜像仍是 0801），
  回滚 = 重启 api 容器。
- 遗留：api 镜像尚未固化（qa_verification 包 + agent_service 为热补），
  待第八节统一重建；canonical-qa /home/qa/.config 密钥为 docker-cp，
  镜像重建后需重新放置（0930e 起的操作步骤固定：mkdir → cp →
  chown qa:qa → chmod 600 → restart）。

## 五、对照验收升级（五.4，2026-09-30）

`scripts/compare_qa_old_new.py` 重构：命题化题集（complex_comparison×2 /
numeric×2 / no_evidence×2 / source_localization×2 / followup×1）+ 三轴评分
（事实正确性 / 证据覆盖 / 引用支持，各 0-2）+ 冻结控制（语料规模、模型、
flags 指纹随报告落盘，`--baseline` 做跨运行一致性告警）。

首轮三方对照（old=tech-db-fresh@8765, new=canonical-qa 0930h@8767，
/tmp/compare_v2_report.json）：**新 51/54（94.4%）vs 旧 43/54（79.6%），
门槛（≥80%）PASS**。唯一失分题：量子恐龙税制混合形态（拒答头+线索清单）
被判 PARTIALLY_SUPPORTED——与旧系统行为一致，属已知语义边界（见第二节）。

## 六、截断召回回归（五.5，2026-09-30）

`scripts/eval_qa_truncation_recall.py`（离线，复用 rebuild 的文本组装与
jieba 分词，2000 条采样 / 914 条正文片段探针 / 人工题 8 条）：

| 变体 | body_recall@25 | vs 800 |
|------|---------------|--------|
| embed ≤800 | 0.6882 | — |
| embed ≤600（当前线上） | 0.6904 | **+0.22pp，无退步** |
| embed ≤200 | 0.6127 | **−7.55pp，超容忍** |
| bm25 ≤200 | 0.6116 | 同级退步 |

- **结论：当前 600/800 截断不造成不可接受召回退步，无需恢复分块或加预算；
  200 字档不可采用**（若未来 CPU 预算再收紧，600 是下限）。
- 摘要兜底实测：b 缺失记录（样本 891/2000=44.5%）的 as 全部是 <100 字
  短桩（418）或全空（473）——正文层本就缺失，短桩兜底对标题自检索
  Δ=0（不伤害也不贡献）；as 兜底的真实价值在「有短摘要可看」而非召回。

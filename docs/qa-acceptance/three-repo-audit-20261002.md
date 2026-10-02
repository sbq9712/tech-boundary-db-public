# 三仓库功能审计（2026-10-02：tech-db / tech-boundary-db / tech-boundary-data-feed）

审计对象与范围：用户提出的 5 项功能完整性。审计人：Claude（全程实际读码 + 运行态检查）；
独立交叉审计：Codex CLI（真实调用，只读，1,118,823 tokens，原文见同目录
`codex-three-repo-audit-20261002.md`）。仓库 HEAD：main@64a1be6。

运行态证据（本机 systemd user 单元）：
- breadth-pipeline.timer：OnCalendar 03,07,11,15,19,23:30（每 4h）✅，近期多次 exit 3（部分成功，见 G9）
- breadth-feed-package.timer：每日 05:00，2026-10-02 推送 2026-10-02.zip（+69359）✅
- techdb-pipeline/data-sync/graph/vector/server/tunnel/auto-update：7 个单元运行于 ~/tech-db-fresh（维护公开站 sbq9712.github.io/tech-db）
- CI（GitHub Actions）：main 上 3 个 workflow 全绿

---

## 逐项结论

### 1. tech-db 完全集成 + 每 4h 自动管线 + 可删库 —— ⚠️ 部分：**现在还不能删**

**已成立**：
- tech-boundary-db 自有管线独立：`scripts/run_breadth_pipeline.sh`（"完全不依赖 tech-db 仓库"）→ `pipeline/auto_pipeline.py`，systemd 每 4h ✅
- 代码层无运行时依赖：仓库内 tech-db 字样均为注释/溯源说明；`scripts/hydrate_breadth_runtime.py` 默认本地恢复，`--legacy-upstream` 为显式可选项（:552）
- QA 基础索引本地重建：`scripts/rebuild_qa_base_index.py`（"无需 tech-db"）、`scripts/refresh_qa_assets.py`（3f58698 已去除依赖）

**不成立 / 阻塞项**：
- 本机仍有 7 个启用的 techdb-* systemd 单元在 `~/tech-db-fresh`（= github.com/sbq9712/tech-db 克隆）上运行：每 2h pipeline、每 30min data-sync（git pull + 推 auto-sync 提交回 GitHub tech-db main）、graph/vector 索引、8765 服务、cloudflared 隧道。**删除 GitHub 仓库后这些单元全部报错**（git pull/push 失败、公开站数据停更）
- `docker-compose.yml:51` 默认映射宿主 8765，与旧 techdb-server 冲突（本机靠 override 8767 规避；新离线机无旧服务，但默认值仍是坑）
- 文档残留：`README.md:16` 引用不存在的 `scripts/auto_update_takeover.sh`；`services/canonical-qa/README.md:66/76/84` 仍指导 `cd /home/rhett/tech-db-fresh`
- 数据漂移：tech-db-fresh lite 69,471 条 vs tech-boundary-db 69,368 条（旧链 2h vs 新链 4h 造成 103 条差），删库前需确认不再需要旧站/旧数据

**结论**：功能已 100% 吸收（管线/索引/QA/分诊全独立），但"放心删库"需要先做一次**退役切换**（停用 techdb-* 单元、清理文档、确认公开站下线决策）——见修复票 T1。

### 2. 每日增量包 → 离线上传 → 三索引自动更新 —— ✅ 主链路完整（4 个隐患）

**已验证**：
- 生成：`scripts/build_feed_package.py` v2（changelog ADD/UPDATE/DELETE + watermark + 公开准入过滤 + 哈希链），每日 05:00 推送 sbq9712/tech-boundary-data-feed（daily/*.zip + LATEST.json，共 7 包；2026-09-28 缺失为 v1→v2 过渡期"当日无变化"，非故障）
- 上传：资料库-广度追踪-GitHub广度情报（app.js:2254，仅 zip、幂等重放、逐项计数）→ `/api/uploads`(section=breadth, source=github) → `github_import.py`（路径/大小/哈希/v2 变更绑定校验）→ `breadth_manual_records` 落表
- 三索引自动更新 ✅：持久队列 `breadth_index_queue.py`（target_key 唯一、指数退避、崩溃恢复）+ api 启动 worker 线程（main.py:51，默认开）→ canonical-qa `/api/index/upsert`（bge-m3 **本地模型**向量+BM25，离线可用，模型已打进镜像 /app/bge-m3-model）+ `mark_fragment_dirty()` 图谱碎片实时推导（graph_fragment.py，含六.5 治理）
- 契约测试：test_feed_v2_import_and_queue / test_github_incremental_import，CI 绿

**隐患（Codex 交叉确认）**：
- G1 增量索引损坏时：启动只清空+打日志（incremental_index.py:79），healthcheck 只断言基础向量/BM25/mapping（docker-compose.yml:53）→ **容器仍"健康"**，已完成的队列任务不会自动重嵌入（静默丢召回）
- G2 空 chunks payload 在队列侧直接返回成功（breadth_index_queue.py:279，静默成功，当前构造难出现但协议上是洞）
- G3 离线服务器"每日更新"操作手册缺失：服务器迁移说明.md / DEPLOY.md / 交付清单均无"下载每日 zip → 资料库上传"流程（只存在于 docs/design/github-incremental-dedup.md）
- G4 生产环境从未实测导入真实包（CI 用合成包）；离线服务器部署本身也未演练
- （运维边界）TECHDB_QA_INDEX_TOKEN 仍为占位符默认值 `replace_with_a_random_internal_index_token`（api↔canonical-qa 内网写入鉴权形同虚设，内网隔离下低危但应换真值）

### 3. 表格逐行/整文件 + 资料日期 + 同步到广度 —— ✅ 已实现（1 个表述差异）

- 逐行/整文件选择 ✅：.xlsx/.csv 添加后弹"表格导入配置"（app.js:2470-2565）：导入方式单选（每行一个情报/整个文件一个情报）+ 工作表选择 + 列映射（标题必填，日期/链接/正文/摘要/等级/来源/分类可选），逐文件独立配置
- 逐行模式无文件级日期 ✅：日期锁定并提示"日期取自每行的日期列，无需文件级日期"（app.js:2595-2599），提交时不发文件日期（:2668）；后端行日期规范化（Excel 序列号/中文日期/带时间），空日期与非法日期分别计数不静默兜底（table_rows.py:154/209+）
- 整文件模式保留文件级日期（合理默认；用户原话歧义处已按此实现）
- 同步上传到广度情报 ✅：仅行业追踪/ATSC 显示（app.js:2359），**默认不勾选（=否）**，勾选后行/文件记录 in_breadth_nav（uploads.py:486-493），广度页经 /api/breadth/manual-records 拉取并按 t|d|u 幂等合并显示（breadth/app.js:737-790，不重复），并经同一持久队列进 QA 索引可被检索 ✅
- 表述差异：同步选项是**上传弹窗内一个整批复选框**（作用于本次全部文件）而非"表格中每文件一列"。功能等价（默认否、后端逐文件持久化 sync_breadth）；如需逐文件列可作 UX 微调（T12，P3）
- 后端防线：广度/github 组合禁入通用弹窗与 row_mode（app.js:2334 / uploads.py:435）；industry/atsc 之外拒绝 sync 标志（uploads.py:349）
- 去重语义注意：content_hash 去重是全库级（不只当前文件），重复行跨文件也会跳过（by design，已在返回计数透出）

### 4. tech-db「数据库问答」迁移到门户问答 —— ⚠️ 后端完整，前端显示退化

**已成立（后端=tech-db 质量链完整移植）**：
- 检索：agent_service → canonical-qa `/api/search` = 编排检索（拆解/多路检索/图谱扩展/novelty 排除/重排/证据评估，server.py:1586；legacy_hybrid 等价实现 retrieval_pipeline.py）
- 答案侧：qa_verification/（epistemic→verifier→claim_mapping→citation_grounding→numeric_facts→有界修复→answer_status→knowledge_boundary）与 tech-db legacy_hybrid 实跑链一致
- SSE：status/token/citations/replace/error/done；前端两处（门户 app.js:1483+、广度 breadth/qa.js）都正确按事件名解析（广度侧为本轮 4d37ee3 修复）
- 会话持久化（DB）/novelty 排除/引用合并、广度页「数据库问答」视图（caf24b2，4 轮 Codex 审查 APPROVE）

**退化/缺口**：
- G5 门户前端丢弃后端验证结论：done 事件里的 `answer_status / knowledge_boundary / claim_check / safety_hits / verification` 后端发送（agent_service.py:919-932）但 app.js:1491 只取 response/citations/retrieval_summary/truncated/finish_reason/fallback_used → **花大功夫做的核验链结论用户看不见**（tech-db 原版 UI 有四态徽章/证据卡/边界提示）
- G6 广度 qa.js 的 reference_cards/claims/evidence_summary/来源角色/快照漂移 UI 空转：canonical done 载荷已不含这些字段（server.py:1458 只发 answer_status/stop_reason/knowledge_boundary/claim_check/safety_hits/evidence/retrieval_trace）→ 旧富证据界面字段读不到值
- G7 门户 app.js:80 markdown 链接未做 scheme 白名单（`javascript:` 注入与引号断开属性，广度 qa.js 已修的同类问题——app.js:224 又把渲染结果拼 innerHTML）
- G8 done 事件长尾（>7min 才发）：验证链在容器内对外 SSL 失败重试拖住 SSE（已知问题，广度/门户两处一致；前端能安全收尾但体验差、浪费连接）

### 5. triage_engine 集成 —— ✅ 完成（1 个运维边界备注）

- vendored：pipeline/triage_engine/（v1.11，上游 a00706e，ENGINE_PROVENANCE.md 溯源，引擎零改动）
- 唯一适配层 engine_triage.py；主入口两个（auto_pipeline.classify_and_score:743 / backfill_unclassified:812）+ 后台脚本（backfill_categories / rerun_engine_retriage）全走适配层；子进程基于包根，无外部克隆路径依赖 ✅
- 口径：领域/载体/类型(tg)/评分(sc)/AI精选(aip) 引擎为唯一来源；全库 69,368 条已重分诊（7+4 展示标签 100% 对齐）
- 备注 G10：LLM 模式会在 vendored 引擎目录写 .env（engine_triage.py:333，0600 + gitignore）——与"零改动引擎目录"的运维边界有轻微出入，建议改为指向外部 workdir
- （Codex 确认无第二生产入口）

---

## 缺口汇总（修复票编号）

| # | 级别 | 问题 | 位置 |
|---|---|---|---|
| G1 | P1 | 增量索引损坏 → 健康 ok、静默丢召回、无自动重嵌入 | incremental_index.py:79、docker-compose.yml:53 |
| G2 | P2 | 空 chunks 任务静默成功 | breadth_index_queue.py:279 |
| G3 | P1 | 离线服务器每日更新操作手册缺失 | 服务器迁移说明.md 等 |
| G5 | P1 | 门户前端不显示 answer_status/knowledge_boundary/claim_check/safety_hits | app.js:1491 |
| G6 | P2 | 广度 qa.js 富证据字段与新 done 契约不对齐（空转/死代码） | breadth/qa.js:825+ |
| G7 | P1 | 门户 app.js markdown 链接注入（scheme 白名单 + 引号编码缺失） | app.js:80 |
| G8 | P2 | done 事件长尾（验证链 SSL 重试拖住流） | qa_verification / config |
| G9 | P2 | qa-index-sync 1 条 update op 永久卡住重试 → 管线每 4h exit 3 显示 Failed | runtime/qa-index-sync/state.json、auto_pipeline.py:1549 |
| G10 | P3 | 引擎 LLM .env 写入 vendored 目录 | engine_triage.py:333 |
| G11 | P1 | tech-db 退役切换未做（7 个 techdb-* 单元仍在跑、文档残留、README 幽灵脚本、compose 默认 8765） | systemd / README.md:16 / services/canonical-qa/README.md:66 / docker-compose.yml:51 |
| G12 | P2 | TECHDB_QA_INDEX_TOKEN 占位符 | .env / .env.example |
| G13 | P3 | 容器内 pytest 集合错误（scripts/ 未进镜像布局） | backend/tests/test_feed_v2_import_and_queue.py:34 |
| G14 | P3 | 同步到广度为整批复选框而非逐文件列（功能等价，UX 可选） | app.js:2347 |
| G15 | P2 | 生产未实测真实包导入 + 离线机未演练 | — |


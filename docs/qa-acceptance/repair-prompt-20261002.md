# 修复指令（粘贴给 Claude Code 使用）——2026-10-02 三仓库审计后

> 以下整段复制粘贴给 Claude Code。粘贴时可把「背景」段落一起带上，效果更佳。

---

你是 Claude Code，在仓库 ~/tech-boundary-db（GitHub: sbq9712/tech-boundary-db，remote main 为权威）中工作。下面是一次独立审计发现的问题清单，请逐项修复。

## 背景（一句话）

tech-db 的功能已全部吸收进本仓库（4h 管线 / QA / 索引 / 分诊均已独立），每日增量包发布到 sbq9712/tech-boundary-data-feed，离线内网服务器经"资料库-广度追踪-GitHub广度情报"上传后自动更新知识图谱/关键词/向量三索引；本轮审计确认主链路完整，但存在以下缺口需要修复，另需为 tech-db 仓库退役做切换准备。

## 工作规则

- 全程不停下来问我裁决；能做就做，不能做的（需我授权的）记录到交付报告并继续其他任务。
- GitHub remote 为权威；每完成一批工作先 `git pull --rebase`（或 fetch+rebase）再 push。
- 禁止：force push、删除数据/仓库/文件历史、提交任何密钥或 .env 内容、修改或删除 ~/tech-db-fresh 及其 systemd 单元（T1 的退役脚本只"生成并演练"，不实际执行停用，除非我在该任务里明确授权）。
- 删改不可逆项一律改为"准备好脚本 + 干跑输出 + 等我确认执行"。
- 每项任务完成必须过自测（pytest / node --test / 构建校验）+ 对照下面的验收标准逐条核对；测试通过≠完成。
- 涉及密钥一律只生成占位符与生成命令，真实值由我手动填入 .env（.env 已 gitignore，永不提交）。
- 修复全程实际调用 Codex CLI 做代码审查（REQUEST_CHANGES 则继续修，直到 APPROVE），禁止代写其意见。

---

## 任务清单（按优先级）

### T1（P1）tech-db 退役切换包 —— 目标：让我之后能放心手动删除 github.com/sbq9712/tech-db

现状：本机仍有 7 个启用的 techdb-* systemd user 单元跑在 ~/tech-db-fresh 上（techdb-pipeline.timer 每 2h、techdb-data-sync.timer 每 30min 会 git pull 且推 auto-sync 提交回 GitHub、graph、vector、server:8765、tunnel、auto-update[已禁用]）；README.md:16 引用不存在的 scripts/auto_update_takeover.sh；services/canonical-qa/README.md:66/76/84 仍写 `cd /home/rhett/tech-db-fresh`；docker-compose.yml:51 默认映射宿主 8765 与旧服务冲突（本机靠未提交的 override 改 8767）。

要求：
1. 新增 `docs/tech-db-retirement.md`：完整的退役核对清单——
   a. 删库前必须确认的项：新链 4h 管线连续 ≥3 个周期成功（`systemctl --user list-timers breadth-pipeline` + journalctl）；最近一次 feed 包发布成功且能下载；QA 基础索引已本地重建（scripts/rebuild_qa_base_index.py）；
   b. 停用顺序：先 `systemctl --user disable --now techdb-tunnel techdb-server techdb-data-sync.timer techdb-pipeline.timer techdb-graph.timer techdb-vector.timer`，再确认 sbq9712.github.io/tech-db 已 404（Pages 需要我在 GitHub 网页上手动关）；
   c. 删库后的验证：tech-boundary-db 全链路（pipeline/feed/QA/上传导入）不出现任何 tech-db 路径报错。
2. 新增 `scripts/techdb_retire.sh`（只生成 + `--dry-run` 演示输出，**不实际执行任何 systemctl**）：逐个 echo 停用命令 + 校验命令 + 预期输出；加 `--execute` 开关但默认拒绝运行除非环境变量 TECHDB_RETIRE_CONFIRM=I-AM-SURE。
3. 文档修正：删除 README.md:16 的幽灵脚本引用（改为指向真实脚本或删掉该行）；services/canonical-qa/README.md 三处 `cd /home/rhett/tech-db-fresh` 改为本仓库路径；docker-compose.yml 默认宿主端口从 8765 改为 8767（并把 override 的临时映射关系写进 README，说明 8765 是旧 techdb-server 遗留）。
4. 数据漂移说明写进 docs/tech-db-retirement.md：旧库 69,471 vs 新库 69,368（差 103 条，因旧链 2h/新链 4h 步调差），列出差异条目查询方法（按 content_hash 对比两库 breadth 表）与"是否需要补齐"的判断标准；默认结论应为"以新库为准，无需补齐"，除非发现新库缺近 7 天数据。
验收：文档齐全；`bash -n scripts/techdb_retire.sh` 通过且 dry-run 输出完整；`docker compose config` 通过；grep 全仓库无 `/home/rhett/tech-db-fresh` 残留（.git 历史除外）；pytest 全绿。

### T2（P1）离线服务器"每日增量更新"操作手册

现状：该流程只存在于 docs/design/github-incremental-dedup.md，运维文档（服务器迁移说明.md、DEPLOY.md、交付清单）里没有。

要求：
1. 在 服务器迁移说明.md 增加"日常数据更新（离线环境）"一章：从 sbq9712/tech-boundary-data-feed 下载 daily/<日期>.zip（或经 U 盘/内网中转拷贝）→ 登录门户 → 资料库 → 广度追踪 → GitHub广度情报 → 上传 zip → 等待"导入成功 N / 跳过 M"结果 → 后台队列自动更新三索引（知识图谱/关键词/向量）→ 如何确认：`GET /api/breadth/index-queue/status`（或等价管理端点）排队=0、失败=0，QA 试搜一条新导入内容能召回。
2. 同步在 DEPLOY.md 与交付清单加交叉引用（指向该章节，不复制全文以免双源漂移）。
3. 写明故障处理：上传报"包已导入"= 幂等重放属正常；上传 400 时的常见原因（非 v2 包/哈希不匹配/解压超时）；队列失败条目如何重试（端点或重启 api 容器后自动恢复）。
验收：三处文档更新且互相引用一致；手册中每个 API 路径/按钮名称与实际代码逐一核对无误。

### T3（P1）增量索引健康自检 + 损坏自动恢复

现状：canonical-qa 启动时若增量索引损坏只清空+打日志（services/canonical-qa/app/incremental_index.py:79 附近）；docker-compose healthcheck 只断言基础向量/BM25/mapping（docker-compose.yml:52-54）；结果容器"健康"但增量召回静默丢失，且已完成的队列任务不会重新嵌入。

要求：
1. `/api/health`（或现有健康端点）增加 `incremental_index_ready` 断言：增量索引文件存在且可加载（加载失败即 unhealthy）。
2. 损坏恢复路径：canonical-qa 清空重建增量索引后，向 api 返回/暴露"需要重放"信号（或在 api 侧检测到 incremental 计数清零）；api 侧把状态=completed 且 embed 时间早于重建时间的队列条目重新置为 pending 重放。若跨服务信号复杂，允许简化为：api 启动及每小时对比 canonical `/api/index/stats` 的 incremental 计数与本队列入表总数，不一致即重放差集——选实现简单且可测的一种，写清取舍。
3. 为上述两条各加契约测试（合成损坏索引文件场景）。
验收：新测试覆盖"损坏→unhealthy→恢复→重嵌入"全路径且通过；现有 healthcheck 相关测试不回归。

### T4（P2）队列空 chunks 静默成功改为失败

现状：services/api/app/breadth_index_queue.py:279 附近，payload chunks 为空时任务直接成功。

要求：空 chunks 且目标不是显式删除语义时，标记任务 failed 并带原因（防协议层吞错）；若确有"空文档合法"场景，需在代码注释写明并加白名单条件。加单测（空 chunks → failed）。
验收：新测试通过；`node --test`/pytest 相关套件全绿。

### T5（P1）门户前端显示核验结论（answer_status / knowledge_boundary / claim_check / safety_hits）

现状：后端 done 事件已发送这些字段（services/api/app/agent_service.py:919-932），但门户前端 web/app.js:1491 的 done 处理只取 response/citations/retrieval_summary/truncated/finish_reason/fallback_used，把用户最关心的核验链结论全丢了（tech-db 原版 UI 有四态徽章/证据卡/边界提示，迁移后退化）。

要求：
1. done 处理补齐字段读取，并在答案下方渲染：
   - answer_status：徽章（已核验/部分核验/未核验/低置信 等后端实际枚举，以后端代码为准）；
   - knowledge_boundary：边界提示条（有内容才显示）；
   - claim_check：逐条声明核验列表（声明文本+通过与否+证据引用 id，可折叠）；
   - safety_hits：安全命中提示（有才显示）；
   - verification：若为耗时/汇总信息，至少展示一行汇总。
2. 渲染必须复用现有 XSS 防线：所有插值走现有转义函数；新增任何动态 href 一律过 scheme 白名单（http/https/mailto，先剥控制字符，%22 编码引号）——直接复用 web/breadth/qa.js 里已实现的 _qaSafeUrl/_qaSafeHref 模式（可抽成共享工具文件，两处引用）。
3. 后端字段缺失时优雅降级（不渲染该区块，不报错）。
验收：手工构造含各字段的 done 事件（单测或本地 mock SSE）验证渲染与降级；`node --test web/tests` 通过；Codex 审查通过。

### T6（P2）广度 qa.js 富证据字段与新 done 契约对齐

现状：web/breadth/qa.js:825+ 读取 reference_cards/claims/evidence_summary/来源角色/快照漂移等字段，但 canonical-qa 现契约的 done 载荷已不含它们（server.py:1458 只发 answer_status/stop_reason/knowledge_boundary/claim_check/safety_hits/evidence/retrieval_trace）→ 旧富证据 UI 空转。

要求（二选一，选 A 优先）：
A. 把 qa.js 的证据区改为消费新字段（evidence/claim_check/retrieval_trace），保留旧 UI 结构换数据源；
B. 若确认旧字段永不回归，删除死代码路径。
禁止保留"读不到数据的半死不活"状态。与 T5 共享渲染组件优先。
验收：广度页「数据库问答」实测（本地起 canonical mock 或真实服务）证据区有内容；`node --test` 全绿。

### T7（P1）门户 app.js markdown 链接注入修复

现状：web/app.js:80 的 markdown 渲染对链接未做 scheme 白名单，`javascript:` 注入与属性引号断开均可能（app.js:224 又把结果拼 innerHTML）；同类问题已在 web/breadth/qa.js 修过（_qaSafeUrl/_qaSafeHref），门户侧漏修。

要求：把 qa.js 的方案（剥控制字符 + scheme 白名单 + %22 编码）抽成共享模块（如 web/assets/lib/safe_url.js），qa.js 与 app.js 同时引用；app.js 所有动态生成 href 的路径（含 T5 新增的）全部过该模块。加单测：`javascript:` / `java\tscript:` / `/a" onmouseover="alert(1)` / `data:text/html` 等用例全被中和。
验收：新增 js 测试通过；现有门户渲染无回归（目测主页/问答页正常）。

### T8（P2）TECHDB_QA_INDEX_TOKEN 真实化流程

现状：api ↔ canonical-qa 内网写入鉴权 token 默认值为占位符 replace_with_a_random_internal_index_token。

要求：
1. 修改代码：检测到 token 仍为占位符默认值时，api 启动打印显著警告（或 canonical-qa 拒绝占位符 token 的写请求，选影响面小的一种）。
2. .env.example 写明生成方法 `openssl rand -hex 32` 与两侧同值配置说明；文档（DEPLOY.md）补充。
3. 不得在任何提交中出现真实 token 值。
验收：占位符路径有测试覆盖；grep 确认无真实 token 入库。

### T9（P2）qa-index-sync 卡死任务 + 管线 exit 3 处置

现状：runtime/qa-index-sync/state.json 有 1 条 update op（id 前缀 8c218bc2）每 4h 重试永久失败，导致 auto_pipeline 以 exit 3（部分成功）结束，systemd 显示 Failed，告警噪音；exit 3 的语义（部分成功）没有文档与 OnFailure 处理。

要求：
1. 诊断该 op 失败根因（读 journalctl 与 state.json 详情），给出修复：能修则修（如目标记录不存在 → 允许配置化跳过并记录审计行），不能自动修则提供 `scripts/qa_index_sync_repair.py --drop-op <id>`（带确认与备份 state.json）。
2. auto_pipeline 对"重试超上限"的 op 做终态化（标记 dead-letter + 告警日志一次），避免每 4h 重复失败。
3. breadth-pipeline.service 加 `OnFailure=` 指向一个仅记录的单元或移除误导性 Failed 显示的说明文档（systemd 层面 exit 3 显示 failed 属预期），并在 docs 写清 exit 码语义（0 全成 / 3 部分成 / 其他失败）。
验收：根因有书面结论；修复或工具就位且有测试/干跑输出；连续两个周期管线 exit 0（或 dead-letter 后 exit 0）。

### T10（P3）杂项代码卫生

1. G10：pipeline/engine_triage.py:333 LLM 模式向 vendored 引擎目录写 .env —— 改为写仓库级临时/workdir 路径（保持 0600），vendored 目录恢复零写入；ENGINE_PROVENANCE.md 补一句说明。
2. G13：backend/tests/test_feed_v2_import_and_queue.py:34 的 parents[2] 假设在容器内不成立导致 pytest 收集错误 —— 修 import 路径（按容器布局回退查找），保证 `pytest` 在容器内能收集；本地与 CI 均绿。
验收：vendored 目录 `git status` 干净（跑一次 LLM 模式路径后）；容器内 pytest 收集零错误。

### T11（P3，可选）同步到广度改为逐文件列

现状：行业追踪/ATSC 上传弹窗的【同步上传到广度情报】是整批复选框（默认否），非逐文件列。
要求：若改动小（配置数组已有 per-file 结构）就改成每文件一列默认否；否则保持现状并在交付报告注明"功能等价，未改"。
验收：勾选行为与后端 sync_breadth 持久化逐文件一致；现有上传测试不回归。

### T12（P2）生产实测真实包导入（一次性演练）

在本地用真实产物演练一次完整离线流程：下载 sbq9712/tech-boundary-data-feed 最新 daily zip → 走"资料库-广度追踪-GitHub广度情报"上传（可用 API 直调，但必须走同一后端入口）→ 确认导入计数、队列清零、三索引计数增长、QA 召回新记录。把结果（含每步证据截图/日志摘录）写入 docs/qa-acceptance/ 目录新报告。
验收：四步证据齐全；如失败，记录根因与修复后重跑。

---

## 收尾要求

1. 全部任务完成后：本地全量自测（pytest + node --test + docker compose config）；
2. `git pull --rebase` 后 push 到 GitHub main（禁止 force push）；push 失败则保留全部本地 commit SHA 并在报告中说明；
3. 实际调用 Codex CLI 对整个变更集做最终审查，循环到 APPROVE 为止；
4. 产出交接包（docs/qa-acceptance/ 下新文件）：任务对照表（每项 DONE/PARTIAL/BLOCKED + 证据链接）、遗留风险、供 ChatGPT 独立复核的要点清单；
5. 不得把 PARTIAL/BLOCKED 写成 DONE。


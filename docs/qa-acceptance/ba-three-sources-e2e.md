# 八：三个源头隔离小样本全链验收（新闻/文献/微信源仓库）

日期：2026-10-01　分支：feature/sectioned-library-ui
 harness：`pipeline/tests/e2e_three_sources_isolated.py`（新增）

## 8.0 「三个源头」的正确语义与本验收的隔离边界

- **源头 = 三个源仓库**（wodewoping-png/news-spider、literature-rss-spider、wechat-daily-news-csv），
  不是管线视图（data/processed 既有产物）、不是重建资产、不是增量卷。
- 本地 HTTP 服务按 GitHub 语义（`/repos/{owner}/{repo}/contents/{path}` 列表 +
  `/{owner}/{repo}/main/{path}` raw 内容）实时供给固定小样本 CSV：
  新闻 3 行 / 文献 2 行 / 微信 2 行（URL 唯一，t|d|u 身份可跟踪）。
- 管线代码拷贝到隔离 stage（`/tmp/e2e3s`，可 `E2E3S_STAGE` 覆盖），从**空 lite 冷启动**，
  不读不写真实 tech-db / breadth / canonical-qa；`BOUNDARY_REPO` 指向隔离目录。
- 离线：`TRIAGE_LLM_OFF=1`（引擎规则分诊）+ 隔离 HOME（无 ZAI key）→
  主题/摘要/关键参数/翻译各 GLM 步**快速如实失败**（`TECHDB_GLM_BACKOFF_DELAYS=0`，
  新增 env 旋钮，默认行为不变），验收断言「无伪造摘要」。`SKIP_CLUSTER=1`（stage 无 2.2G 模型缓存）。

## 8.1 复现缺陷与修复（全部由本验收暴露，已修复并验证）

| # | 缺陷（已复现） | 修复 | 验证 |
|---|---|---|---|
| 1 | `merge_and_rebuild` 无条件 `open(LITE_PATH)`：冷启动（processed/ 为空）即 `FileNotFoundError`，首次部署/重建场景全链不可用 | `LITE_PATH` 不存在时基线视为空集（auto_pipeline.py） | 阶段 A 冷启动 rc=0、7 条入库 |
| 2 | `build_snapshot` → `load_manifest()`：无既有 manifest-data.js 时冷启动崩溃 | 缺失时从空 manifest 结构开始（build_snapshot.py） | 阶段 A 发布出 manifest+3 分片族 |
| 3 | `dedup_conferences.py`：extract 首轮无候选时不写 conferences.json，去重步即崩（每轮 WARN） | 文件缺失 → 0 条空转完成（dedup_conferences.py） | 阶段 A 后续轮次无 WARN |
| 4 | `build_breadth_alert_snapshot.py` 只读旧 `manifest.json`；现行数据契约为 `manifest-data.js`（category_counts 早已双模式，alert 漏改）→ 真实发布链上旧 manifest 一旦消失/未生成即 FATAL，state 不提交 | 对齐 category_counts 的双模式读取（manifest-data.js 优先，回退旧 json，皆无→空 meta） | stage rc=0；真实仓库 rc=0（10 条 alert，输出与既有逐字节一致，`git status` 干净） |

管道行为缺陷 1/2 属「已复现」；缺陷 4 在真实仓库曾依赖旧 manifest.json 兼存才未爆，
为已复现的隐性回归（隔离冷启动暴露）。

## 8.2 阶段与断言（24/24 通过，退出码 0）

运行：`timeout 570 python3 -u pipeline/tests/e2e_three_sources_isolated.py`
（2026-10-01 05:18–05:20，全程 <2 分钟；证据：`docs/qa-acceptance/logs/ba-e2e-three-sources-final.log`、
`.../ba-e2e-three-sources-stageE-run.log`）

- **A 冷启动三源入库**：rc=0；lite 恰 7 条；新闻/微信按 t 命中；文献载体 `i=l`；
  引擎分诊落地（分类/不相关，非全部未分类）；**无伪造摘要**（离线降级如实）。
- **B 记录更新**：改写新闻 a1 正文 → 日志出现 `[rev]`（Step 2b 记录级 diff upsert），
  正文含「提升40%」，总数仍 7（不重复入库）。
- **C 记录删除**：微信源删 1 行 → w2 从 lite 移除，总数 6。
- **D 新增文件**：新闻 articles-2026-09-16.csv → 新记录入库，总数 7。
- **E QA 三路索引同步**：真实 `scripts/sync_qa_index.py` → 隔离替身（`TECHDB_QA_SYNC_URL`）：
  「基线条目 0；差异：新增 7；批次 0/0：7 条 → ready；状态已落盘 runtime/qa-index-sync/state.json」。
- **F 发布区契约**：manifest records_total=7；lite/meta/summary 分片族非空；
  `.pipeline_state.json` 已知文件 news=1/literature=1/wechat=1（只提交成功文件）。

## 8.3 与既有验收的衔接（复用，不重复开发）

- 记录更新/删除的**旧包残留、同版本冲突、并发 worker、迟到任务**：六.4 发布锁 +
  崩溃恢复合同测试已覆盖（`services/canonical-qa/qa-backend/tests/`，容器内复跑见 wu7）。
- 同步中断重试：本验收 E（SKIP→补推收尾）+ 六.4 water-mark 未持久化恢复测试。
- 表格双模式/同步选项/sheet/权限：三（wu2-embed-audit.md 所在验收线）已交付。
- 容器重建 + 离线导入：七.2 隔离容器复验（wu7-image-and-ci.md）。

## 8.4 边界与未验证项（如实）

- 本验收为**小样本隔离链路验收**：GLM 步为无 key 快速失败（不验证 LLM 产出质量），
  聚类步跳过（模型缓存不在 stage），嵌入为 QA 侧增量索引替身（未触真实 bge-m3 资产）。
  样本通过**不**写成生产全量重建通过。
- 真实门户多轮问答 + 期望证据 QA：LLM key 已配置 ≠ 可达（离线降级路径已在七.2 验证
  retrieval 可用、`llm_configured` 状态如实呈现），端到端 LLM 回答质量**缺少验收证据**。
- 生产态（真实 GitHub 源 + 真实 canonical-qa 8767）的 Step 10 同步未在本验收触碰，
  以免写入真实索引；生产时序依赖 breadth-pipeline.timer / breadth-feed-package.timer
  （既有 systemd 配置，已核对存在）。

## 8.5 真实服务链多轮检索 + 期望证据 + 如实降级（隔离容器，2026-10-01 补充）

对象：qa-iso-1001（techdb-canonical-qa:1001，隔离卷 qa_iso_*，端口 8768）；
api-iso-1001（techdb-api:1001，空库隔离 pg，端口 8001）；agent-iso-1001（同镜像只读 agent，端口 8769）。

- **统一检索（基础 68,523 + 增量 509）**：`GET /api/search` 多查询探针全部返回；
  期望证据命中——上传文档《病毒通道视紫红质钙抑制的分子机制研究》
  （94 chunks，kind=upload）在 `/api/chat/stream` 引用列表第 17 位（sim 0.016），
  同主题基础文献 [23][24][25] 同列；容器内直查增量索引 cosine 0.62 排第一。
- **如实降级（无 LLM key ≠ 伪造）**：`/api/chat/stream` 检索段完整（25 条 citations），
  生成段错误信息明确：
  `QA LLM API key is not configured; retrieval-only mode is available, but chat or
  graph-ingest generation requires TECHDB_QA_LLM_API_KEY`——不产出编造回答。
  第二轮（追问）同样检索成功 + 同一降级错误，服务无副作用。
- **门户链（api→readonly-agent HTTP）**：`POST /api/assistant/query` →
  `agent_connected`，agent 对空库如实返回"未在当前只读知识库或情报数据库中找到足够
  匹配的信息"（空库诚实降级，非异常）。
- **暴露并修复的缺陷（隔离复现）**：`backend/app/main.py` 启动引导中
  `seed_domains_if_empty`（依赖可选 /data/domains.json）抛异常会把
  `seed_users_if_empty` 一并跳过 → 库中无任何用户、无人能登录。已修复为域种子
  独立容错；修复后隔离容器 admin 正常引导、登录/建会话/助手链路 200。

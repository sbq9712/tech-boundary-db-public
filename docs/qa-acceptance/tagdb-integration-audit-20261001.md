# TagDB → 广度追踪页面 完整接入审计 + triage_engine 功能替代审计（2026-10-01）

任务来源：用户要求认认真真核对两件事——
A. **TagDB（tech-db）是否完整接入广度追踪页面**；
B. **triage_engine 仓库功能是否已替代广度页面（即 TagDB）中对应的功能**。

## A. TagDB → 广度页面接入清单（逐项核对）

tech-db 原生广度页 = 4 个视图：广度情报总表 / 日报周报月报 / 会议日历 / **数据库问答**。
数据链 = tech-db auto_pipeline（抓取→GLM分类/评分→摘要→聚类→GitHub 发布）。

| # | tech-db 能力 | 本仓状态 | 证据 |
|---|---|---|---|
| A1 | 广度情报总表（69k 记录、分片装载、聚类、AI摘要） | ✅ 完整 | pipeline/auto_pipeline.py 独立管线直产；:8080 实测 69,368 条装载、50 卡渲染 |
| A2 | 日报/周报/月报 | ✅ 完整 | breadth/data/reports/ + 报告视图实测可切 |
| A3 | 会议日历 | ✅ 完整 | conferences.json + calendar 视图实测可切 |
| A4 | **数据库问答视图（qaView/qaSidebar/qa.js 1408 行）** | ❌ **此前缺失 → 本次补齐** | 见下「本次修复」 |
| A5 | 情报类型 新闻/文献 子类弹窗 | ✅ 本次修复 | triage_engine v1.11 展示分类（新闻7类+文献4类），计数+勾选过滤实测通过 |
| A6 | 领域分类树 | ✅ 本次找回 | 根因同 A4 前的布局 bug（多余 </div>） |
| A7 | 知识库资料上传 → 广度可检索 | ✅ 完整 | 门户上传「同步上传到广度情报」→ breadth/manual-records API → app.js 合并装载；canonical-qa 增量索引（incremental_records=973） |
| A8 | 数据管线（CSV 抓取/去重/翻译/主题/摘要/聚类/发布） | ✅ 完整迁入 | pipeline/auto_pipeline.py 含全部对应函数（diff 核对：新增 publish_to_boundary/generate_topics/会议抽取/持久队列，git_push 由镜像发布取代） |

### A4 本次修复（数据库问答视图完整接入）

- **HTML**（breadth/index.html）：view-tabs-second「数据库问答」页签、qaSidebar（新建对话/历史对话）、
  qaView（图谱、示例问题、消息区、输入区）——与 tech-db 原生结构一致。
- **qa.js**（breadth/qa.js，tech-db 原版移植）：唯一改动 = API 层。原版直连 qa-backend :8765（无鉴权，
  cloudflare 隧道）；移植后走同源认证代理 `/api/breadth/qa/*`，token 复用门户 `auth_token`（iframe 同源）。
  会话管理（localStorage 50 条）、SSE 流式解析、图谱 Canvas、引用/证据卡逻辑与原版一致。
- **后端**（backend/app/routers/breadth_qa.py，新增）：`POST /api/breadth/qa/chat/stream`（SSE 逐块转发，
  不整包缓冲）、`GET /api/breadth/qa/graph`、`GET /api/breadth/qa/stats`；Bearer 鉴权
  （无 token 实测 401）；上游不可用映射 502/503 公开口径。测试 6/6 通过（backend/tests/test_breadth_qa_proxy.py）。
- **部署**：canonical-qa 补 `TECHDB_QA_LLM_API_KEY`（.env，来源宿主 ZAI key，未在任何输出中显示）。
- **e2e 实测（:8080）**：stats ✓（69,496 条索引）；graph ✓（nodes/edges）；chat/stream ✓
  （「固态电池」问句 → 25 引用 → 1,759 字带 [n] 引用标注答案流式下发）。
- **CSS**：styles.css 与 tech-db 的 135 条 qa-* 规则逐条一致（无缺漏），未改动。

## B. triage_engine 替代 TagDB 对应功能清单

引擎 v1.11（pipeline/triage_engine/，唯一对接面 pipeline/engine_triage.py）：

| # | TagDB 原实现 | 替代状态 | 证据 |
|---|---|---|---|
| B1 | GLM 分类提示词（领域/载体/类型） | ✅ 已替代 | auto_pipeline.classify_and_score → engine_triage（2026-09-28 起）；全库 69,368 条已按引擎展示链重分诊（新闻 21,829 / 文献 47,539，7+4 标签交叉表 100% 对齐） |
| B2 | GLM 评分 | ✅ 已替代 | 引擎 S8 value/10 + 评分卡维度 → sc/scd |
| B3 | AI 精选判定 | ✅ 已替代 | 新闻 S8 档位 高/中 → aip；文献一律不精选（数据实测 aip=1 仅新闻 3,943 条） |
| B4 | 未分类 self-heal | ✅ 已替代 | backfill_unclassified → engine_triage（旧 GLM 分类提示词已退役） |
| B5 | 主题/翻译/摘要/聚类 | ➖ 引擎无此功能，保留 GLM/本仓实现（语义不变） | 引擎定位是分诊，不是生成 |

**结论：A、B 两个方向均已收口。** B1-B4 引擎为唯一来源（新旧两套分类不会同时生效）；
A1-A8 中唯一的缺口 A4（数据库问答视图）本次补齐。

## 遗留已知项（非本次引入，均先于本次改动存在）

1. **问答 done 事件长尾**：canonical-qa 答案侧核验链（五.1/五.2）在答案流完后仍持有 SSE 连接
   （实测 >7 分钟未发 done；门户问答 /api/assistant/stream 同样 >100 秒未收口）。
   答案文本与引用已完整下发，前端流结束即定稿（qa.js reader done 分支）；
   状态徽章（已核验/UNVERIFIED）在 done 前不显示。canonical-qa 日志显示核验 LLM 调用
   `SSL: UNEXPECTED_EOF_WHILE_READING`（容器内 urlopen 出网被断），建议后续单独排查。
2. backend 测试套件在本机挂载形态下有 2 个收集错误 + deploy_image_contract 3 失败
   （stash 前后复测相同，先于本次改动存在；与镜像内路径 /backend 有关）。

## 回滚

- 代码：git revert 本次提交（breadth/index.html 恢复 3 视图、无 qa.js 引用；main.py 去掉 breadth_qa 注册）。
- 部署：`.env` 的 `TECHDB_WEB_IMAGE_TAG`/`TECHDB_API_IMAGE_TAG` 回 `1003`/`1002` 后 `docker compose up -d api web`。
- 配置：`.env` 删除 `TECHDB_QA_LLM_API_KEY` 一行（canonical-qa 回到仅检索无生成）。

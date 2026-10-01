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

## 附：Codex 审查第 2 轮（2026-10-02，4d37ee3 收口）

对 79999f0 / caf24b2 / 3f58698 的 Codex CLI 审查结论为 REQUEST_CHANGES，
4 项必修全部落实（提交 4d37ee3，techdb-web/api:1005 部署实测）：

| 必修项 | 落实 |
|---|---|
| 上游错误体透传 + history 无界契约 | 代理错误改固定口径（状态码 + 公开文案）；history 限 role/content/20 条/8k，扩展字段剥离；exclude_ids 白名单 + 200 上限 + int 归一 |
| 前端 SSE 忽略事件名（replace/error 被丢弃） | sseFrameParser 事件名感知派发；error 显式失败；流式 401 兜底 |
| markdown `javascript:` 链接 | 链接 scheme 白名单（http/https/mailto 或相对），引用 URL 同样过 `_qaSafeUrl` |
| 测试缺口 | pytest 10 项（三端点 401、5/7 字节硬切分字节级透传、错误体不泄露、契约边界）+ Node 13 项（tests/js/test_qa_sse_parser.mjs，切分重组/replace/error/done/idx=0/链接白名单） |

审查同时确认了根因分析：修复前 57/59 div 失衡、修复后 71/71。
MINOR/NIT 项处置：Dockerfile div 守卫定位为回归告警（注释/动态 HTML 可绕过，
已注释说明）；refresh_qa_assets.py 的 upstream_commit 为注释明示的兼容别名；
app.js renderMarkdown 的同款链接问题先于本次改动存在（portal 页面，另行处理）。

环境备注：codex 依赖的本地 :4567 Responses 代理（systemd 用户服务
codex-zai-proxy.service）在审查时已停止，重启后恢复（此后审查为真实调用，
token 用量 1,213,429）。

## 附：Codex 复审 R2–R4（2026-10-02，1b4e75a 及后续收口）

- R2（REQUEST_CHANGES）：URL 控制字符混淆（`java\tscript:`/NUL 前缀）、SSE 空行
  未复位事件名、exclude_ids 白名单拒绝真实语料 URL（约 6,246 条会 422）→
  1b4e75a 修复（控制字符清洗、空行复位+CRLF、三形态收敛校验）。
- R3（REQUEST_CHANGES，1 项）：escHtml（textContent→innerHTML）不转义引号，
  相对 URL 中 `"` 可断开 href 属性注入 `onmouseover` → 修复为 %22 编码 +
  引用卡片统一 `_qaSafeHref`（部署 techdb-web:1007）。
- R4（**APPROVE**）：注入闭合确认、`_qaSafeHref` 与链接分支安全等价、
  回归测试 24/24 真实通过。仅 INFO 级备注（一处冗余断言，不影响结论）。

审查均为真实调用（z.ai 经本地 :4567 Responses 代理，codex-zai-proxy.service）。

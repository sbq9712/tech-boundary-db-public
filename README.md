# 技术边界数据库

技术情报收集、知识管理与 AI 问答平台。

## 这个仓库是什么

本仓库的 `main` 分支是**活动开发版**（工作区内对应目录 `#DEV`），日常开发全部发生在这里。它**不是**任何一次服务器交付的快照。

- **最新稳定 tag**：`v260801.2`（2026-08-03，已交付公司服务器，对应 `techdb-*:0801` 系列镜像）。
- **`main` 已远超该 tag**：0804 问答补丁、0807 分类健壮化、0818 判断树试点、2026-09 门户/资料库/深度调研改版、广度追踪 tech-db 收编（125 叶子分类法）等。这些改动已进库，但**尚未打新稳定 tag、尚未部署服务器**。
- 因此：clone 本仓库得到的是开发中代码；要复现服务器上运行的 0801 版本，应 checkout `v260801.2`。
- 版本、tag 与交付事件的完整对照：[docs/版本索引.md](./docs/版本索引.md)。

## 当前状态（2026-09-22）

- **广度追踪数据源由本仓库自持**（2026-10 起 tech-db 已退役）：上游数据经 [sbq9712/tech-boundary-data-feed](https://github.com/sbq9712/tech-boundary-data-feed) 每日发布包交付，走「资料库 → 广度追踪 → GitHub 广度情报」导入（离线环境日常更新流程见 [服务器迁移说明.md](./服务器迁移说明.md)）；本仓库自有管线（`pipeline/` + `scripts/run_breadth_pipeline.sh` + systemd user timer `breadth-pipeline.timer`）负责分类/评分与发布。tech-db 退役流程与核对清单见 [docs/tech-db-retirement.md](./docs/tech-db-retirement.md)。
- **门户/资料库/深度调研 UI 完成 2026-09 改版**：侧边栏点击式收起/展开、历史对话折叠、上传弹窗表格化（逐文件元数据）、行业图景树样式修复。契约测试见 `backend/tests/test_portal_ui_contract.py`。

## 快速开始（开发者）

```bash
git clone https://github.com/EDMUNDSdaONE/tech-boundary-db.git
cd tech-boundary-db

# 1. 本地开发环境变量（与生产 .env 是两套，勿混用）
cp .env.example .env.local
#    至少填入：TECHDB_AGENT_API_KEY / TECHDB_AGENT_BASE_URL / TECHDB_AGENT_MODEL
#    （公司内网 OpenAI 兼容网关的密钥与地址，向项目负责人索取）

# 2. 启动开发栈（api + readonly-agent + web，从源码构建，不依赖交付镜像）
./start_with_local_ai.sh
```

首次启动说明：

- `start_with_local_ai.sh` 用 `docker compose up --build` 从当前源码构建镜像，与服务器上预构建的 `techdb-*:0801` 交付镜像无关。
- canonical QA 的模型与索引资产**不在 Git 内**，开发栈不启动该容器不影响 api/web 前后端开发；需要完整问答联调时见下文"外部资产"。
- 数据库 schema 用 Alembic 管理（当前 head：`0020_upload_embedding_state`），首次启动自动迁移。

协作前必读：[docs/CONTRIBUTING.md](./docs/CONTRIBUTING.md)（分支、commit 规范、入库红线、自检清单）。

## 部署到服务器（另一条路径）

服务器部署**不使用本仓库直接构建**，而是使用离线交付物（镜像 tar + 代码包 + 补丁包），当前生产版本为 0801 基础包 + 0804 问答补丁。交付物清单、目录布局与逐步流程见 [DEPLOY.md](./DEPLOY.md) 与工作区 `06_交付/0804/服务器部署启动流程.md`（该文件在仓库外，含敏感信息说明，不入仓）。

## 功能

- **情报管理** — 技术情报的收集、分类、标注、审核
- **行业图谱** — 交互式行业技术地图
- **仪表盘** — 行业赛道分析视图生成
- **个人研究 Agent** — 账号级会话、正式知识索引、证据引用与 SSE 流式问答
- **知识库集成** — 与 Obsidian vault 联动
- **资料入库** — 管理员上传、服务器持久落盘、广度追踪 77 类自动分类、鉴权下载
- **深度调研试点** — 判断树方法论（`pilot/`，含 SOFC、核聚变两个竖井与 HTML 认知面板）

## 技术栈

**后端**：FastAPI + PostgreSQL 16 + SQLAlchemy + Alembic
**前端**：Vanilla JS + Nginx
**AI**：公司内网 OpenAI 兼容端点（默认 CATL AI 网关，支持可配置模型列表）

**部署**：Docker Compose 五服务容器化，canonical QA 模型与索引随独立镜像离线交付。

Canonical QA 的可审计运行源码和离线构建清单位于 `services/canonical-qa/`；大模型、索引和记录资产不进入 Git，只随 `techdb-canonical-qa` 镜像离线交付（资产契约与 pin 值见 `external-data/qa-assets/README.md`）。

## 架构

```
Nginx (:8080)
  ├── 白名单静态前端镜像 (HTML/JS/CSS)
  └── /api/ → FastAPI (:8000)
                ├── 情报 CRUD、上传落盘、77 类分类与增量 embedding 编排
                ├── 用户范围会话与公司模型生成
                └── Docker 内网调用 canonical-qa (:8765)
                     ├── 镜像内既有 bge-m3 + 向量 + BM25 基线索引
                     └── Docker 卷中的上传资料增量向量/BM25 索引

PostgreSQL 16 (容器内部 :5432)
上传对象 (${TECHDB_UPLOAD_HOST_PATH} -> /app/uploads)
readonly-agent (:8765 容器内部；:8766 为兼容宿主机端口)
```

## 数据模型

19 张业务表，核心包括 `info_items`、`domains`、`sources`、`knowledge_artifacts`、`uploaded_files` 和 `users`。上传 embedding 状态作为 `uploaded_files` 的字段维护；新上传采用广度追踪 125 叶子分类目录，历史行业图景保留为快照。

"文件落盘"指对象写入服务器持久目录且数据库登记 SHA-256；"资料入库"指该文件已得到分类终态；只有 `embedding_status=ready` 才代表新资料已进入问答检索。门户以 canonical QA 的既有基线索引为基础，并在其上融合上传资料增量索引；不重建或修改基线资产。完整术语定义见 [CONTEXT.md](./CONTEXT.md)。

## 项目文档

| 文档 | 内容 |
|---|---|
| [DEPLOY.md](./DEPLOY.md) | 服务器部署（离线交付物路径） |
| [API接口说明.md](./API接口说明.md) | API 文档 |
| [数据字段与表结构.md](./数据字段与表结构.md) | 表结构 |
| [部署与运行说明.md](./部署与运行说明.md) | 详细运行说明 |
| [docs/CONTRIBUTING.md](./docs/CONTRIBUTING.md) | 协作约定：分支、commit、入库红线 |
| [docs/版本索引.md](./docs/版本索引.md) | 版本、tag 与交付事件对照 |
| [docs/技术边界数据库_NEXT_SESSION.md](./docs/技术边界数据库_NEXT_SESSION.md) | 项目状态 handoff |
| [CONTEXT.md](./CONTEXT.md) | 领域术语表 |
| [docs/adr/](./docs/adr/) | 架构决策记录（ADR 0001–0011） |

## 外部资产（有意不入仓的部分）

仓库只含 Git 跟踪的源码与配置模板，以下内容按 `.gitignore` 与版本管理规范第 5 节**有意排除**：

| 缺失内容 | 补齐方式 |
|---|---|
| 开发环境变量 | `cp .env.example .env.local` 后填入内网网关配置；**不要提交** |
| 生产 `.env` | 单独安全传输到服务器，绝不入仓（见 CONTRIBUTING 第 4 节红线） |
| 知识库快照、delivery views、chatbot 包 | 按工作区 `支撑资料/` 的 `support-manifest.json` 清单获取，放入 `external-data/` 对应子目录 |
| canonical QA 模型与索引 | 只随 `techdb-canonical-qa` 镜像离线交付，契约见 `external-data/qa-assets/README.md` |

## 协作

两位开发者（EDMUNDSdaONE、sbq9712）均具 write 权限。小改动（docs/fix）可直推 `main`；功能改动请走 feature 分支 + PR。详见 [docs/CONTRIBUTING.md](./docs/CONTRIBUTING.md)。

© 2026 技术边界数据库项目


### Docling 上传资料与溯源

上传资料使用 Docling 文档理解、OCR/表格结构与 HybridChunker，保留原文件、Markdown、Docling JSON、chunks 和 provenance，再接入现有 bge-m3 / BM25 / Agentic RAG。安装、模型准备、canonical 代码层升级及测试方式见 [文档摄取说明](docs/document-ingestion.md)。

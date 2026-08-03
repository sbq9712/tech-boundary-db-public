# 技术边界数据库 0801（`v260801.2`）

技术情报收集、知识管理与 AI 问答平台。

## 快速部署

在已导入交付镜像的服务器上：

```bash
docker load -i techdb-api-0801.tar
docker load -i techdb-canonical-qa-0801.tar
docker load -i techdb-readonly-agent-0801.tar
docker load -i techdb-web-0801.tar
docker load -i postgres-16.tar
cp .env.example .env
# 编辑 .env，填入密码和公司内网模型配置
./deploy.sh
```

访问 http://localhost:8080

详细说明见 [DEPLOY.md](./DEPLOY.md)

## 功能

- **情报管理** — 技术情报的收集、分类、标注、审核
- **行业图谱** — 交互式行业技术地图
- **仪表盘** — 行业赛道分析视图生成
- **个人研究 Agent** — 账号级会话、正式知识索引、证据引用与 SSE 流式问答
- **知识库集成** — 与 Obsidian vault 联动
- **资料入库** — 管理员上传、服务器持久落盘、广度追踪 77 类自动分类、鉴权下载

## 技术栈

**后端**：FastAPI + PostgreSQL 16 + SQLAlchemy + Alembic  
**前端**：Vanilla JS + Nginx  
**AI**：公司内网 OpenAI 兼容端点（默认 CATL AI 网关，支持可配置模型列表）

**部署**：Docker Compose 五服务容器化，canonical QA 模型与索引随独立镜像离线交付

Canonical QA 的可审计运行源码和离线构建清单位于 `services/canonical-qa/`；大模型、索引和记录资产不进入 `main`，只随 `techdb-canonical-qa:0801` 镜像交付。

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

19 张业务表，核心包括 `info_items`、`domains`、`sources`、`knowledge_artifacts`、`uploaded_files` 和 `users`。上传 embedding 状态作为 `uploaded_files` 的字段维护；新上传采用广度追踪 77 项分类目录，历史行业图景保留为快照。

“文件落盘”指对象写入服务器持久目录且数据库登记 SHA-256；“资料入库”指该文件已得到分类终态；只有 `embedding_status=ready` 才代表新资料已进入问答检索。门户以 canonical QA 的既有基线索引为基础，并在其上融合上传资料增量索引；不重建或修改基线资产。

## 项目文档

- [DEPLOY.md](./DEPLOY.md) — 部署说明
- [API接口说明.md](./API接口说明.md) — API 文档
- [数据字段与表结构.md](./数据字段与表结构.md) — 表结构
- [部署与运行说明.md](./部署与运行说明.md) — 详细运行说明

© 2026 技术边界数据库项目

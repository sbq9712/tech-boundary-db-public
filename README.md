# 技术边界数据库 v260723

技术情报收集、知识管理与 AI 问答平台。

## 快速部署

```bash
tar -xzf techdb-v260723.tar.gz
cd v260723
cp .env.example .env
# 编辑 .env，填入 TECHDB_AGENT_API_KEY
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

## 技术栈

**后端**：FastAPI + PostgreSQL 16 + SQLAlchemy + Alembic  
**前端**：Vanilla JS + Nginx  
**AI**：OpenAI 兼容端点（已验证 GLM-5.1，支持可配置模型列表）  
**部署**：Docker Compose 四服务容器化

## 架构

```
Nginx (:8080)
  ├── 静态前端 (HTML/JS/CSS)
  └── /api/ → FastAPI (:8000)
                ├── 情报 CRUD
                ├── 图谱与仪表盘
                └── 调用 readonly-agent (:8765)
                      └── AI 检索增强 (知识库 + chatbot 包)

PostgreSQL 16 (容器内部 :5432)
```

## 数据模型

18 张表，核心：`info_items`、`domains`、`sources`、`dashboards`、`alerts`、`users`。

## 项目文档

- [DEPLOY.md](./DEPLOY.md) — 部署说明
- [API接口说明.md](./API接口说明.md) — API 文档
- [数据字段与表结构.md](./数据字段与表结构.md) — 表结构
- [部署与运行说明.md](./部署与运行说明.md) — 详细运行说明

© 2026 技术边界数据库项目

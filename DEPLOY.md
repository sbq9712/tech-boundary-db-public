# 技术边界数据库 — 部署说明

## 前提条件

- Docker >= 24
- Docker Compose V2（`docker compose` 命令）
- 2GB 以上内存，10GB 以上磁盘

---

## 快速启动（3 步）

```bash
# 1. 解压
tar -xzf techdb-v260629.0.tar.gz
cd v260629.0

# 2. 配置 API Key（唯一必填项）
cp .env.example .env
nano .env   # 或 vim .env，填入 TECHDB_AGENT_API_KEY

# 3. 一键部署
./deploy.sh
```

访问 http://localhost:8080

---

## 配置说明

`.env` 中只有一项必填：

| 变量 | 必填 | 说明 |
|------|------|------|
| `TECHDB_AGENT_API_KEY` | ✅ | AI 模型的 API Key |

其余有默认值，按需修改：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TECHDB_AGENT_BASE_URL` | Z.AI coding endpoint | AI API 端点 |
| `TECHDB_AGENT_MODEL` | `glm-5.2` | 模型名称 |
| `TECHDB_AGENT_MAX_RETRIES` | `2` | 上游 429 短退避重试次数 |
| `TECHDB_AGENT_RETRY_BASE_DELAY_SECONDS` | `2` | 重试基础等待秒数（默认等待 2、4 秒） |
| `TECHDB_WEB_PORT` | `8080` | 前端端口 |
| `TECHDB_KB_PATH` | `./external-data/knowledge-base` | 知识库路径 |
| `TECHDB_DELIVERY_VIEWS_PATH` | `./external-data/delivery-views` | 交付视图路径 |
| `TECHDB_CHATBOT_PACKAGE_PATH` | `./external-data/chatbot-package` | Chatbot 包路径 |

---

## 数据目录

部署包内置了 `external-data/` 目录，包含三个子目录：

| 目录 | 内容 | 大小 |
|------|------|------|
| `knowledge-base/` | Obsidian 知识库全文 | ~380MB |
| `delivery-views/` | 交付视图与知识文档 | ~96MB |
| `chatbot-package/` | 索引、RAG、质检报告 | ~825MB |

如果数据放在其他位置，在 `.env` 中指定绝对路径覆盖默认值。

---

## 服务说明

| 服务 | 端口 | 说明 |
|------|------|------|
| `web` | 8080 | Nginx 前端 + API 反向代理 |
| `api` | 8000 | FastAPI 主后端 |
| `readonly-agent` | 8765 | 只读 AI 查询服务 |
| `db` | — | PostgreSQL 16（容器内部） |

服务间通过 Docker 网络通信，`web` 通过 `api:8000` 反向代理，`api` 通过 `db:5432` 连接数据库。

---

## 切换 AI 模型

`.env` 中修改三行即可切换：

**用 OpenAI**：
```
TECHDB_AGENT_API_KEY=sk-xxx
TECHDB_AGENT_BASE_URL=https://api.openai.com/v1
TECHDB_AGENT_MODEL=gpt-4o
```

**用 Claude（兼容端点）**：
```
TECHDB_AGENT_API_KEY=sk-xxx
TECHDB_AGENT_BASE_URL=https://api.anthropic.com/v1
TECHDB_AGENT_MODEL=claude-sonnet-4-20250514
```

修改后运行 `docker compose restart api readonly-agent`。

---

## 常用操作

```bash
# 查看服务状态
docker compose ps

# 查看实时日志
docker compose logs -f api

# 停止服务（保留数据）
docker compose down

# 完全清除（删数据卷，谨慎）
docker compose down -v

# 重新构建
docker compose build && docker compose up -d
```

---

## 故障排查

**端口被占用**：修改 `.env` 中的 `TECHDB_WEB_PORT`。

**数据库迁移失败**：`docker compose exec api alembic upgrade head`

**AI 不回复**：检查 `.env` 中 API Key 和 BASE_URL 是否匹配。日志看 `docker compose logs api`。

**知识库检索为空**：确认 `external-data/knowledge-base/` 非空。

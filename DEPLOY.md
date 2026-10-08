# 技术边界数据库部署说明

## 前提

- Linux 服务器，Docker 24+，Docker Compose V2
- x86_64 Linux 服务器，建议至少 8GB 内存；磁盘需覆盖六个镜像（约 12GB 解压后）、PostgreSQL 和上传资料
- 公司内网或本地 OpenAI 兼容模型端点
- GitHub Release `server-20261004` 提供的六个镜像分片（qa=1008、api=1019、readonly-agent=1019、web=1017、postgres:16、alpine:3）与六类数据资产；服务器部署不依赖公网构建或下载模型
- 装载：`cat <镜像>.tar.gz.part-* | gunzip | docker load`（`docker-images` 分支已废弃）

## 首次部署

```bash
cp .env.example .env
openssl rand -hex 32
# 编辑 .env：填写 SECRET_KEY、数据库/管理员密码、模型配置和上传目录
./deploy.sh
```

生产环境建议：

```env
TECHDB_UPLOAD_HOST_PATH=/srv/techdb/data/uploads
TECHDB_API_BIND=127.0.0.1
TECHDB_AGENT_BIND=127.0.0.1
TECHDB_AGENT_PORT=8766
TECHDB_QA_SERVICE_URL=http://canonical-qa:8765
# CPU 环境首次加载 bge-m3 约需 50 秒，检索超时需留足余量。
TECHDB_QA_SERVICE_TIMEOUT_SECONDS=120
TECHDB_QA_INDEX_TIMEOUT_SECONDS=300
TECHDB_QA_INDEX_TOKEN=<随机内部写入令牌>
TECHDB_QA_INCREMENTAL_VOLUME=techdb_qa_incremental_0033
# MTU：公司 Linux 默认 1500（TECHDB_DOCKER_MTU）；WSL 内跑 Docker 需 1410
```

`deploy.sh` 会创建并检查上传目录、准备 PostgreSQL 卷、优先复用已导入的交付镜像（默认 tag 见 `.env.example`，qa=1008/api=1019/agent=1019/web=1017），并执行 Alembic 迁移（当前 head `0033`）。只有镜像缺失或 `TECHDB_FORCE_BUILD=true` 时才从源码构建。访问入口为 `http://<服务器>:8080`。

## 持久数据

| 数据 | 位置 | 说明 |
|---|---|---|
| PostgreSQL | `${TECHDB_PG_VOLUME}` Docker 卷 | 元数据、分类状态、校验和 |
| 上传对象 | `${TECHDB_UPLOAD_HOST_PATH}` | 必须是服务器持久盘目录 |
| canonical QA 资产 | `techdb-canonical-qa:1008` 镜像 + `graph-live.tar.gz` 挂载 | 内置 bge-m3、基线索引、jieba；图谱经只读挂载；不在服务器下载 |
| Docling 模型 | `external-data/document-models`（Release `document-models.tar.gz`） | api 解析 PDF/DOCX 的本地模型，bind-mount |
| 上传增量索引 | `${TECHDB_QA_INCREMENTAL_VOLUME}` Docker 卷 | 新资料的 bge-m3 向量、BM25 和 chunk 元数据；不修改基线 |
| 知识库 | `${TECHDB_KB_PATH}` | 只读挂载 |
| 交付视图 | `${TECHDB_DELIVERY_VIEWS_PATH}` | 只读挂载 |
| Chatbot 包 | `${TECHDB_CHATBOT_PACKAGE_PATH}` | 只读挂载 |

代码升级不能删除 PostgreSQL 卷或上传对象目录。容器内的 `/app/uploads` 不是配置项；Compose 始终把宿主机目录挂载到这里。

## 分类目录

新上传使用广度追踪 77 项目录，版本记录在 `breadth/data/taxonomy-manifest.json`。旧行业图景位于 `data/legacy-taxonomy/`，仅用于历史展示，不对历史资料做全量重分类。新上传在分类后自动分块并调用 canonical QA 的内部 embedding 接口；被判定为“不相关”或无法提取文本的文件不进入向量索引。canonical QA 以既有索引为基线，不能用旧 Markdown 或 Chatbot 包静默替代。

## Canonical QA 资产边界

`techdb-canonical-qa:1008` 固定 bge-m3 revision 与基线向量/BM25 索引、jieba 字典，基线 68,523 条记录；`graph-export.json` 由 compose 只读挂载（Release `graph-live.tar.gz`）。启动时校验索引映射，失败则拒绝就绪，避免引用错文。该容器只负责检索，门户 API 负责使用公司内网模型生成回答，因此 QA 容器不需要 Z.AI 或其他 LLM 密钥。不要在服务器运行上游 `setup.sh`，也不要使用 Cloudflare 或任何本机转发地址。

## 备份与恢复

```bash
./scripts/db_backup.sh
./scripts/db_restore.sh backup/techdb_YYYYMMDD_HHMMSS.sql.gz
```

备份会同时生成匹配的 `uploads_YYYYMMDD_HHMMSS.tar.gz` 和校验清单。恢复脚本会自动寻找同时间戳文件归档、停止写入服务、恢复数据库并替换上传目录；原上传目录保留为 `.pre-restore.*`。没有匹配文件归档时会明确警告，数据库单独恢复不能保证下载可用。

## 验收

```bash
docker compose ps
docker compose exec -T api alembic current
curl http://localhost:8080/api/health
curl -I http://localhost:8080/.env
curl -I http://localhost:8080/.git/config
curl -I http://localhost:8080/backend/app/main.py
```

预期迁移为当前链头（2026-10-04 交付集为 `0033`，以 `alembic current` 实际输出为准），健康检查返回 `{"status":"ok"}`，三个敏感路径返回 404。再使用管理员账号从上传页完成一次真实上传，检查服务器目标目录、资料库分类状态、`embedding_status=ready` 和鉴权下载。

## 日常数据更新（离线环境）

服务器不拉外网 Git：每日广度增量从 [sbq9712/tech-boundary-data-feed](https://github.com/sbq9712/tech-boundary-data-feed)
下载 daily zip，走门户「资料库 → 广度追踪 → GitHub 广度情报」上传导入，
随后确认导入计数、索引任务队列清零与 QA 增量索引增长。完整步骤与故障处理
（幂等重放/400 包不合规/队列重试）见 [服务器迁移说明.md](./服务器迁移说明.md) 第 7 章。

## 常用命令

```bash
docker compose logs -f api
docker compose up -d --no-build
docker compose down              # 保留数据
```

不要在生产环境执行 `docker compose down -v`，它会删除 PostgreSQL 数据卷。

# 技术边界数据库部署说明

## 前提

- Linux 服务器，Docker 24+，Docker Compose V2
- x86_64 Linux 服务器，建议至少 8GB 内存；磁盘需覆盖五个镜像、PostgreSQL 和上传资料
- 公司内网或本地 OpenAI 兼容模型端点
- `docker-images` 分支提供的五个镜像 tar；服务器部署不依赖公网构建或下载模型

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
TECHDB_QA_INCREMENTAL_VOLUME=techdb_qa_incremental_0801
```

`deploy.sh` 会创建并检查上传目录、准备 PostgreSQL 卷、优先复用已导入的 `0801` 镜像，并执行 Alembic 迁移。只有镜像缺失或 `TECHDB_FORCE_BUILD=true` 时才从源码构建。访问入口为 `http://<服务器>:8080`。

## 持久数据

| 数据 | 位置 | 说明 |
|---|---|---|
| PostgreSQL | `${TECHDB_PG_VOLUME}` Docker 卷 | 元数据、分类状态、校验和 |
| 上传对象 | `${TECHDB_UPLOAD_HOST_PATH}` | 必须是服务器持久盘目录 |
| canonical QA 资产 | `techdb-canonical-qa:0801` 镜像 | 内置 bge-m3、既有索引、记录与图谱；不在服务器下载 |
| 上传增量索引 | `${TECHDB_QA_INCREMENTAL_VOLUME}` Docker 卷 | 新资料的 bge-m3 向量、BM25 和 chunk 元数据；不修改基线 |
| 知识库 | `${TECHDB_KB_PATH}` | 只读挂载 |
| 交付视图 | `${TECHDB_DELIVERY_VIEWS_PATH}` | 只读挂载 |
| Chatbot 包 | `${TECHDB_CHATBOT_PACKAGE_PATH}` | 只读挂载 |

代码升级不能删除 PostgreSQL 卷或上传对象目录。容器内的 `/app/uploads` 不是配置项；Compose 始终把宿主机目录挂载到这里。

## 分类目录

新上传使用广度追踪 77 项目录，版本记录在 `breadth/data/taxonomy-manifest.json`。旧行业图景位于 `data/legacy-taxonomy/`，仅用于历史展示，不对历史资料做全量重分类。新上传在分类后自动分块并调用 canonical QA 的内部 embedding 接口；被判定为“不相关”或无法提取文本的文件不进入向量索引。canonical QA 以既有索引为基线，不能用旧 Markdown 或 Chatbot 包静默替代。

## Canonical QA 资产边界

`techdb-canonical-qa:0801` 固定到上游提交 `fdffba1` 和 bge-m3 revision `5617a9f`，内置并校验向量/BM25 索引、jieba 字典、图谱、59,717 条记录和 24,091 条索引元数据。启动时会修复并验证分片重建导致的记录下标漂移；映射失败则拒绝就绪，避免引用错文。该容器只负责检索，门户 API 负责使用公司内网模型生成回答，因此 QA 容器不需要 Z.AI 或其他 LLM 密钥。不要在服务器运行上游 `setup.sh`，也不要使用 Cloudflare 或任何本机转发地址。

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

预期迁移为 `0020_upload_embedding_state (head)`，健康检查返回 `{"status":"ok"}`，三个敏感路径返回 404。再使用管理员账号从上传页完成一次真实上传，检查服务器目标目录、资料库分类状态、`embedding_status=ready` 和鉴权下载。

## 常用命令

```bash
docker compose logs -f api
docker compose up -d --no-build
docker compose down              # 保留数据
```

不要在生产环境执行 `docker compose down -v`，它会删除 PostgreSQL 数据卷。

# 技术边界数据库部署说明

## 前提

- Linux 服务器，Docker 24+，Docker Compose V2
- 2GB 以上内存；磁盘容量需覆盖广度数据、PostgreSQL、知识库和上传资料
- 公司内网或本地 OpenAI 兼容模型端点
- `docker-images` 分支提供的四个镜像 tar，或可访问的镜像构建环境

## 首次部署

```bash
cp .env.example .env
openssl rand -hex 32
# 编辑 .env：填写 SECRET_KEY、数据库/管理员密码、模型配置和上传目录
# canonical QA 就绪后再填写 TECHDB_QA_SERVICE_URL
./deploy.sh
```

生产环境建议：

```env
TECHDB_UPLOAD_HOST_PATH=/srv/techdb/data/uploads
TECHDB_API_BIND=127.0.0.1
TECHDB_AGENT_BIND=127.0.0.1
TECHDB_AGENT_PORT=8766
# 同机运行上游 QA 时可通过该地址从 API 容器访问宿主机的 8765。
TECHDB_QA_SERVICE_URL=http://host.docker.internal:8765
```

`deploy.sh` 会创建并检查上传目录、准备 PostgreSQL 卷、优先复用已导入的 `0801` 镜像，并执行 Alembic 迁移。只有镜像缺失或 `TECHDB_FORCE_BUILD=true` 时才从源码构建。访问入口为 `http://<服务器>:8080`。

## 持久数据

| 数据 | 位置 | 说明 |
|---|---|---|
| PostgreSQL | `${TECHDB_PG_VOLUME}` Docker 卷 | 元数据、分类状态、校验和 |
| 上传对象 | `${TECHDB_UPLOAD_HOST_PATH}` | 必须是服务器持久盘目录 |
| canonical QA 服务 | `${TECHDB_QA_SERVICE_URL}` | 独立服务，承载上游既有检索索引 |
| 知识库 | `${TECHDB_KB_PATH}` | 只读挂载 |
| 交付视图 | `${TECHDB_DELIVERY_VIEWS_PATH}` | 只读挂载 |
| Chatbot 包 | `${TECHDB_CHATBOT_PACKAGE_PATH}` | 只读挂载 |

代码升级不能删除 PostgreSQL 卷或上传对象目录。容器内的 `/app/uploads` 不是配置项；Compose 始终把宿主机目录挂载到这里。

## 分类目录

新上传使用广度追踪 77 项目录，版本记录在 `breadth/data/taxonomy-manifest.json`。旧行业图景位于 `data/legacy-taxonomy/`，仅用于历史展示，不对历史资料做全量重分类。新上传的 embedding 当前未启用；canonical QA 则只消费其既有索引，不能用旧 Markdown 或 Chatbot 包静默替代。

## Canonical QA 资产边界

门户问答需要独立的 `sbq9712/tech-db` QA 服务。远端上游已提供压缩向量/BM25 索引、jieba 字典和图谱导出；`all-records-lite.json` 不在提交中，但可由仓库内 30 个分片和官方脚本恢复。完整 `bge-m3` 模型、公司 API 适配和 QA 服务镜像仍不随 0801 应用交付。不要直接把上游 `setup.sh` 用于公司服务器：它绑定 Z.AI、用户目录密钥、Hugging Face 下载和临时 Cloudflare 地址。待资产所有者提供模型并完成公司 API 适配后，再配置 `TECHDB_QA_SERVICE_URL`。在此之前门户会返回“检索服务未配置”，不会回退到旧知识源。

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

预期迁移为 `0019_clear_legacy_conversations (head)`，健康检查返回 `{"status":"ok"}`，三个敏感路径返回 404。再使用管理员账号从上传页完成一次真实上传，检查服务器目标目录、资料库分类状态和鉴权下载。

## 常用命令

```bash
docker compose logs -f api
docker compose up -d --build
docker compose down              # 保留数据
```

不要在生产环境执行 `docker compose down -v`，它会删除 PostgreSQL 数据卷。

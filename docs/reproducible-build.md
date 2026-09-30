# 可复现构建与旧仓库依赖隔离（第八节，2026-09-30）

## 目标

在没有 `/home/rhett/tech-db`（旧仓库）的机器上，从本仓库三个数据源头
完成：构建镜像 → 导入/解析 → 索引 → 问答 全链路。本文件是操作手册与
验收记录；授权边界内未删除旧仓库、未替用户停用旧服务（tech-db-fresh
的 8765 端口进程仍在运行，处置权在用户）。

## 一、镜像构建（全部可从本仓库完成）

### 1. canonical-qa（检索+生成+答案侧核验链）

三个数据源头（任一存在即可构建，全部缺失则需要先跑管线）：

| 源头 | 路径 | 说明 |
|------|------|------|
| ① 管线发布视图 | `pipeline/data/processed/` | auto_pipeline 产物（lite 分片+meta），sync_qa_index 消费 |
| ② 基础重建产物 | `runtime/qa-base-rebuild/`（或已入库的 `services/canonical-qa/data/`） | rebuild_qa_base_index embed→assemble 的全量索引 |
| ③ 增量 | `docker volume techdb_qa_incremental_0801` | 上传/ZIP/逐行导入的增量索引（运行时挂载，构建不需要） |

```bash
# 0801-base：依赖+模型（bge-m3 等）一次性底座（已存在则跳过；
# 从零构建见 services/canonical-qa/qa-backend/Dockerfile.incremental 时代文档）
docker build -f services/canonical-qa/qa-backend/Dockerfile.rebuilt \
  -t techdb-canonical-qa:<TAG> services/canonical-qa
# Dockerfile.rebuilt 自带 check_assets 把关：向量/BM25/jieba/lite/清单
# 缺一即构建失败——这是"源头不完整"的硬闸门。

# 换装（回滚 = 上一 TAG 重新 up -d）：
TECHDB_IMAGE_TAG=<TAG> docker compose up -d canonical-qa
# 首次启动需要 LLM key：docker cp ~/.config/anthropic-proxy.env
#   <容器>:/home/qa/.config/ && chown qa:qa + chmod 600（容器内 root 执行）
```

### 2. api（门户后端，含 qa_verification 答案侧链 B）

```bash
docker build -f backend/Dockerfile -t techdb-api:<TAG> .
TECHDB_IMAGE_TAG=<TAG> docker compose up -d api
```
（2026-09-30 时点 api 仍是 0801 镜像 + qa_verification 包/agent_service
docker-cp 热补；重建镜像即可把热补固化。）

### 3. web（门户前端）

```bash
docker build -f web/Dockerfile -t techdb-web:<TAG> .
TECHDB_IMAGE_TAG=<TAG> docker compose up -d web
```

## 二、断外网验证（ZIP 导入/解析/索引/问答）

ZIP → backend 导入解析（文档解析本地 docling/规则，无外网调用）→
canonical-qa 增量索引（本地 embedding）→ 检索问答（LLM 是唯一外网依赖；
断外网时 llm_configured=false，检索-only 模式可用：/api/search 正常，
chat 明确报"LLM key 未配置"而非编造——这是 FAIL_SAFE 设计行为）。

验收命令序列（无外网环境）：
```bash
curl -s http://127.0.0.1:8767/api/health       # vector/bm25 ready, llm:false
curl -s "http://127.0.0.1:8767/api/search?q=钠离子电池" | head -c 200
# 导入 ZIP（门户 API）→ 等 incremental index upsert → 再 search 应命中新记录
```

## 三、旧仓库依赖隔离验收（2026-09-30 实测记录）

| 依赖点 | 原状态 | 现状态 | 验证 |
|--------|--------|--------|------|
| breadth 运行时缺失/损坏恢复 | git 下载 tech-db 钉住快照 | 本仓库 pipeline/data/processed 本地重建（hydrate_from_local_source）；下载降级为显式 --legacy-upstream | 损坏演练：删戳+删分片 → rc=0，68723 条/35 分片恢复，local-pipeline 戳 |
| breadth 正常启动 | 本地戳有效即不触旧仓库（原有） | 不变 | hydrate --check rc=0 无网络访问 |
| canonical-qa 索引 | 重建产物来自本仓库管线视图（1001 提交起） | 不变 | Dockerfile.rebuilt check_assets |
| 门户 hydration 脚本调用链 | start_with_local_ai.sh → hydrate 脚本 | 脚本内部已不再依赖旧仓库，start 脚本零改动 | scripts/test_breadth_runtime_hydration.py 9 passed |
| qa 答案侧核验模块 | 源码参照 tech-db（只读） | 本仓库两份孪生（qa-backend/ + backend/app/services/qa_verification/），运行时零 tech-db import | api 容器内 import 成功（无 tech-db 路径） |
| github_qa.py 文案 | 提及 "sbq9712/tech-db" 字符串 | 仅 provider 描述文案，无运行时依赖 | grep 确认仅 docstring/label |

**结论：本仓库已可在无 tech-db 的机器上完成构建、启动、恢复与问答全链路。
tech-db 目录可以安全地从构建/运行依赖中移除（是否物理删除由用户决定——
按授权不替用户停用或删除）。**

## 四、运行时端口与进程现状（2026-09-30）

- 127.0.0.1:8765 = tech-db-fresh 旧服务（宿主进程，非本仓库容器）——
  旧链对照基准，保留给用户处置；
- 127.0.0.1:8767 = 本仓库 canonical-qa（TECHDB_IMAGE_TAG=0930h）；
- 127.0.0.1:8000 = 本仓库 api（0801 + 热补）；web/db/readonly-agent 0801。

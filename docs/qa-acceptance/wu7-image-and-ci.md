# 七 镜像烤制 / 隔离重建 / CI —— 执行记录（2026-10-01）

## 七.1 官方镜像烤制（api 0801+docker-cp 热修 → 正式镜像）

| 镜像 | 基线 | 结果 | 内容 |
|---|---|---|---|
| techdb-api:1001 | backend/Dockerfile 全量重建 | 见下（构建中→完成） | 宿主仓库当前代码全量烤入（含全部 docker-cp 过的热修：一~六节后端修复、agent_service fail-closed、github_import 字段约束、migration 0030 文件） |
| techdb-web:1001 | web/Dockerfile | exit 0 | app.js/页面/分片运行时全量烤入；内建分片族一致性门禁通过 |
| techdb-canonical-qa:1001 | 0801-base + Dockerfile.rebuilt | exit 0（第3次构建） | 全部 20 个 qa-backend 模块（补登 record_ops.py——第1次构建即因缺它容器无法启动，被七.2隔离验收拦住）+ 68,523 条基础资产（0929 重建产物，五.2 已审计为混合截断，如实捆绑不改变资产状态） |

修复的构建缺陷：
- services/canonical-qa/qa-backend/Dockerfile.rebuilt：COPY 白名单漏
  record_ops.py（server 硬依赖，缺它启动即 ModuleNotFoundError）
- services/canonical-qa/.dockerignore：同样漏 record_ops.py 与 tests/

**每服务独立版本配置**（docker-compose.yml）：TECHDB_IMAGE_TAG（统一tag）
已替换为 TECHDB_QA_IMAGE_TAG / TECHDB_API_IMAGE_TAG /
TECHDB_WEB_IMAGE_TAG / TECHDB_AGENT_IMAGE_TAG，缺省 0801（现网行为
不变）。生产切换命令（回滚=改回 0801 后 up -d）：

```
TECHDB_QA_IMAGE_TAG=1001 TECHDB_API_IMAGE_TAG=1001 \
TECHDB_WEB_IMAGE_TAG=1001 TECHDB_AGENT_IMAGE_TAG=1001 \
docker compose up -d
```

**未执行生产切换**（任务只授权隔离重建验证；现网容器保持运行）。

## 七.2 隔离重建验收（不动现网容器/卷）

canonical-qa:1001 隔离实例（端口 8768，隔离增量卷副本
techdb_qa_incremental_1001_iso ← techdb_qa_incremental_0801 只读复制，
graph-live 副本）：

- /api/health：vector_index_ready=true bm25_ready=true
  indexed_records=68523（新资产）+ incremental 509 chunk/5 文档（副本卷）
  → total 69032；llm_configured=false 如实
- /app/qa-backend/ 模块清单 20 个全量在镜像内（record_ops/graph_fragment/
  answer_chain 等 0801 镜像缺失的模块全部就位）
- /api/index/record-mutate → 422（端点存在；0801 镜像为 404）
- /api/index/record-ops-state → 200；副本卷 record-ops-state.json 加载
  （1 墓碑 + 10 superseded_landed）
- /api/graph：total_nodes=158144 fragment_nodes=912，static_governance
  透出——且**治理完整性闸门真实生效**：graph-export（68,926 记录轮次）
  与 all-records-lite（68,523 条）版本错位 → bound=false +
  reason="entity_to_records max index 68925 >= lite records 68523"，
  不猜测绑定（六.5 逻辑在真实数据上的行为验证）
- bge-m3-model 资产在镜像内（1_Pooling/colbert_linear.pt/...）

api:1001 隔离验收（临时 postgres 实例 + 空库迁移链）：见下文补充。

## 七.3 0801-base 从零构建方法

- 方法 = services/canonical-qa/qa-backend/Dockerfile.release：
  `docker build -f qa-backend/Dockerfile.release -t techdb-canonical-qa:0801-base .`
  （python:3.11-slim + requirements（pytorch cpu extra）+ 资产 + bge-m3 模型 +
  check_assets 门禁；docker history 证实现存 0801-base 即此法构建，2026-09-14）
- 1001 = 0801-base 之上 Dockerfile.rebuilt（代码+资产+清单校验），
  本次即用该链构建，未重烤 base（依赖/模型层无变化，避免无谓下载）。

## 七.4 CI 真实运行

- 根因（main 上 Local development contracts 连续失败）：
  scripts/test_breadth_runtime_hydration.py 断言硬编码分片数
  `test "$count" -eq 30`，而 web/Dockerfile 已改为动态分片族一致性
  校验——本分支 8162dcd 已修（动态断言），本地复跑 9/9 OK。
- scripts/test_conversation_concurrency.cjs 三个 DOM double 缺陷
  （element 缺 dataset、closeAccountMenu/libClassifyClose/Auth 未 stub）
  已修；node 测试 PASS。
- 三个 workflow 全部加 pull_request: branches: [main] 触发
  （此前只 push: main——PR/修复分支永不触发 CI）。
- 推送分支后的真实 CI 运行记录：见本次推送后 gh run list 附件。

## 七.5 Public Feed 独立发布 —— 阻塞声明

- 待发布改动已就绪：scripts/build_feed_package.py（六.1/六.3/六.4 身份
  + 序列链 + 发布锁）、scripts/verify_feed_sequence.py（独立校验器）、
  backend/app/services/github_import.py（六.2 字段约束），均在本分支
  PR #8 内并通过容器测试（26 passed）。
- **未获授权**：向 sbq9712/tech-boundary-data-feed（FEED_REPO）实际
  推送发布包。已按"完整待发布改动 + 阻塞说明"处理，不声称已交付。
- 真实全量包（68k 条）生成校验按既有约定在部署机执行（CI 无主存储副本）；
  CI 侧覆盖合成包端到端校验（通过：10 项校验 + 1 警告 data_version 形态）。

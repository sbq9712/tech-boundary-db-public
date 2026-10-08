# 离线模拟验收证据（T7/T8/T9，2026-10-07~08）

> 环境：WSL 主机（离线等效演练）。项目 offsim20261004 = git archive e4eeb6a（交付集
> 配置）+ 数据资产解包 + 独立卷（offsim_pg_data/offsim_qa_incremental）+ 独立端口。
> **期间主机意外重启一次**，顺带验证了主机重启后全栈可恢复（A14 加强）。
> 交付镜像集最终版：qa=1008、api=1019、readonly-agent=1019、**web=1017**（nginx
> resolver 修复，见 A14 缺陷）、postgres:16、alpine:3。

## A1 平台/指纹（linux/amd64）

| 镜像 | image ID |
|---|---|
| techdb-canonical-qa:1008 | sha256:d4baf7f9b23b39e1b687a6577ba816efafbbcdd0240fd684507ffacf618ac5e6 |
| techdb-api:1019 | sha256:8245e3ed8dac39622692790f0ccf430de0d77bdda5b0bd82b68ab6610e772429 |
| techdb-readonly-agent:1019 | sha256:d66855c1c60a2fe99b99a719a2bfc7f0cb8c3f7e5bfc990b1fa22fa8d12e1ec3 |
| techdb-web:1017 | sha256:422332339a37cf25aa0e8ed25b0a1bcd66189f5f80902ea93bb6c1da59ef726c |
| postgres:16 | sha256:5a65324fe84dc41709ff914e90b07f3e2f577073ed27bf917d4873aca0c9ec51 |
| alpine:3 | sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 |

分片流校验：每镜像 `cat 分片 | sha256sum` 与 `.stream.sha256` 一致（1019 两镜像
导出后即验；其余在导出时已验，SHA256SUMS 于 Release 汇总）。

## A2-A7 栈健康

- A2：五服务 Up，db/canonical-qa healthy。
- A5：`alembic current` = `0033_origin_section (head)`（快照恢复后 api 启动自动迁移到 0033）。
- A7：`/api/health` = `{"status":"ok"}`。
- QA `/api/health`：vector/bm25/mapping/incremental 全 true、incremental_corrupt=false、
  total_records=68523（基线）、增量 1953→1956 记录 / 18→21 文档（演练中增长，见 A10-A13）。

## A8 敏感路径 404

`/.env` `/.git/config` `/backend/app/main.py` `/scripts/db_backup.sh` → 全 404。

## A9 分类目录

`/api/uploads/taxonomy`（鉴权后）：categories=127、business=125、labels={未分类,不相关}。

## A10/A11 feed 导入链路（离线）

- 真实包 `2026-10-04.zip`（gh 下载，sha256 d71af0ff…）：导入成功，幂等撞库跳过 565
  （快照已含该日数据——语义正确，重放无害）。
- 合成包 offsim-synth-20261007.zip（v1 契约、manifest.records_sha256 自洽、2 条）：
  - 导入响应「导入 2 条」；A11 队列：processing→done（223→225，无 pending/新增 failed）；
  - QA 增量索引：incremental_records 1953→1955、documents 18→20；
  - 三路召回：QA `/api/search` 命中合成记录（is_relevant=true）。
- 预存 failed=3 任务为主栈快照带入的 2026-09-29 crash-test 残留（非交付缺陷）。

## A12 问答召回（离线检索 + 生成分离）

- 无网关：citations 命中当日合成情报（25 条引用含 offsim 合成记录）；
  生成侧明确降级报错「QA LLM API key is not configured; retrieval-only mode…」
  —— 检索不受网关影响，生成依赖网关（A16 ✓）。

## A13 文档上传（P0 修复实证）

- A13a 无网关：上传 LibreOffice 生成 PDF（手写最小 PDF 会被 Docling 拒绝——属测试
  文档问题，模型加载正常）→ classification=failed（error=SSL 网关不可达）+
  primary_category=未分类 + **embedding=ready**（chunks=1，index documents_found=1、
  vector_ok/bm25_ok/content_hash_ok 全 true）；QA `/api/search` 按「OFFSIM 离线验收
  文档」召回该上传文档。
- A13b 模拟内网网关（host:18888 OpenAI 兼容 mock，含 classify JSON/分类 JSON/SSE 流）：
  - TECHDB_QA_LLM_BASE_URL/KEY 配置 → llm_configured=true，SSE token 流完整，
    答案「根据库内证据 [1]…500Wh/kg [1]」（answer_status=UNVERIFIED 属 mock 语义，
    全链连通已证）。
  - 分类补齐：网关可用后 `POST /uploads/{id}/classification/retry` →
    classification=classified（合法叶子类目）+ embedding 保持 ready（P0 修复的
    「失败→恢复」闭环）。
- 下载：恢复演练后经鉴权下载 sha256=d81b3d2e… 与上传一致。

## A14 重启持久化 + 发现并修复 nginx 缺陷

- 整栈 `docker compose restart`：数据/索引/alembic 不变（QA ready、incr 21/1956）。
- **发现缺陷**：restart api 后经 web 的 /api/ 全量 502（容器内直连 api:8000 正常）。
  根因：nginx 启动时解析 upstream 域名并缓存 IP，api 容器重建换 IP 后旧缓存失效。
  **修复**：nginx.conf 增加 `resolver 127.0.0.11 valid=10s` + 变量形式 proxy_pass
  （$api_upstream/$qa_upstream），重建 **techdb-web:1017**；复测 api 重启后立即 200。
  契约测试 test_nginx_re_resolves_api_upstream_after_container_restart 入库。
- 主机重启（意外断电级）：docker daemon 恢复后 offsim/主栈均拉起成功；主栈
  web/canonical-qa 需手动 up（未配 restart=always，属部署注意事项，已入文档）。

## A15/A21 备份演练

offsim 栈 `db_backup.sh`（alpine 容器打包）三件套 6 秒生成；宿主普通用户
`sha256sum -c backup_20261008_053617.sha256` 全 OK（root 属主归档 644 可读，A21 ✓）。

## A16 网关不可用模式

见 A12/A13a：导入/索引/检索全不受影响；生成与分类明确降级报错，不崩溃、不挂起。

## A17 manifest.json

见 Release server-20261004（T10 产出后回填核对结论：字段与 SHA256SUMS/指纹矩阵一致）。

## A18 internal 网络双向断言

- 出站（internal:true 覆盖）：容器内 `socket.create_connection(('1.1.1.1',443))` →
  Network is unreachable；DNS 解析 github.com → gaierror。
- 入站（普通网络阶段）：宿主访问 web:18080=200、agent:18766=200。
- 注：Docker 的 internal 网络不支持端口发布（无 NAT 网关），离线模拟分两阶段
  （internal 阶段断言出站隔离；普通阶段断言端口可用），公司真实环境外层网络本身
  无公网路由，等效成立。

## A19 恢复语义（T9）

- 恢复前停写服务（stop api readonly-agent）；数据库 DROP/CREATE + `psql
  --single-transaction` 单事务重建；uploads 旧目录保留为 `uploads.pre-restore.*`
  （两代保留，人工清理）；QA 卷经 alpine 解包后 canonical-qa 重启自动加载。
- 恢复后断言：api health ok、QA ready（incr 21/1956 不丢）、uploaded_files=11、
  分类补齐结果保留（classified）、鉴权下载 200 且 sha256 一致。

## A20 代码一致性

- offsim app = git archive e4eeb6a（当期 HEAD）；api/agent 1019 镜像内 /app/app 与
  091a1f8 工作树一致（P0 修复生效即证）。终版 commit 以 Release manifest.json
  `code_commit` 为准（T10 后 GitHub/GitLab 同 SHA 核对命令见交付清单）。

## T8 升级模拟（0801→0033）

- 0801 镜像对空卷 alembic upgrade → 实测 head=**0026_github_incremental_import**
  （SPEC 原写 0020 属猜测，已按实测修订）。
- 造数：users=1、uploaded_files=1 → pg_dump。
- 1019 栈（独立项目 offsim_upg2）恢复该 dump → api 启动自动 0027→…→0033 七步
  迁移全执行、无错误；数据在（1/1）；全栈 healthy。

## T11 回归测试矩阵（2026-10-08，HEAD f18c8b7/fb6a90a，镜像代码 9908ce0）

宿主直接全量 pytest 会因环境依赖挂起/超时，按「测试归属环境」分环境执行；
每个宿主失败均已定位根因并在归属环境复验通过：

| 套件 | 归属环境 | 结果 |
|---|---|---|
| test_deploy_image_contract（8） | 宿主 repo 根 | 8 passed |
| test_classification/dashboard/delivery_intel/fail_closed/health/hermes/import_deep_research/model_catalog/qa_answer_chain/qa_verification/readonly_agent/record_ops/table_row_upload/agent_service（合计 ~117） | 宿主 | 全 passed |
| test_conversations_pagination(6)/library_role_permissions(10)/portal_qa_stream_regression(6)/breadth_manual_records(11)/table_row_types(26)/github_incremental_import(4)/origin_section_attribution(5)/repair_row_types(4)/upload_index_status(19) | 宿主 + 临时 postgres:16（alembic 0033，55432） | 全 passed |
| test_api_endpoints（34） | 宿主 + 临时 DB + mock 模型目录 | 33 passed；industry_map 在 api:1019 镜像内 passed（backend/data 仅镜像内） |
| test_document_ingestion（22） | 混合：宿主（jieba 有）+ api:1019（docling 有） | 并集全过（宿主 16P+2P；镜像内 19P；host 5F=docling 缺失、镜像 2F=jieba 缺失，互为环境补集） |
| test_upload_ingestion（31） | 宿主 + api:1019 | 28 passed；3 docling 失败在镜像环境归属 |
| test_portal_ui_contract（9） | web:1017 容器网络（http://web） | 9 passed |
| test_breadth_qa_proxy（11） | 宿主 + TECHDB_QA_SERVICE_URL | 10 passed；1 预存测试漂移（上游体现在带 sources=["breadth"]，测试断言早于 f349f19 三源范围功能，两文件均未被 091a1f8..9908ce0 触及） |
| test_feed_v2_import_and_queue（36） | 宿主 + 独立全新 DB | 35 passed；1 预存测试漂移（test_queue_old_upsert_cannot_overwrite_new_delete：_execute 自 3c8375c 起对 delete 任务追加 _post_record_mutate_delete 墓碑屏蔽调用，测试未 mock 该调用致 HTTP 失败重试；生产路径 canonical-qa 真实存在 record-mutate 端点不受影响） |
| test_incremental_reset_replay（9） | 宿主 + 独立全新 DB | 9 passed（污染共享库时 1 例计数偏移，全新库全过） |

结论：除 2 个预存测试漂移（test_breadth_qa_proxy sources 字段、test_feed_v2
record-mutate 未 mock；均有 git 历史证据证明早于本次交付范围，且生产路径
不受影响——QA 服务真实存在对应端点/字段语义）外，全部测试在归属环境通过。
宿主「失败」均为环境缺失（postgres/docling/jieba/web 服务/模型网关），
已在对应容器环境复验。

Codex 评审（实际调用，非代写）：
- final-review（/tmp/codex-logs/final-review.log，o4 档）：唯一发现 [P3]
  服务器迁移说明.md:123 宿主 QA 端口 8765→8767。已采纳修复（f18c8b7）。
- rescue 回归（/tmp/codex-logs/rescue.log）：追溯发现 deploy.sh:229 QA_PORT
  默认与部署与运行说明.md:11/83 同类问题。已采纳修复（fb6a90a），
  deploy 契约测试 8 passed 复测通过。

## 环境备注（复现要点）

- 端口规划：web 18080、qa 18767、agent 18766、api 127.0.0.3:8000（主栈占 127.0.0.1:8000；
  主机重启后 docker 残留 127.0.0.2:8000 stale proxy，无 sudo 清不掉——换绑回环别名绕过）。
- offsim .env 与 docker-compose.offline.yml（internal 网络覆盖）在演练中生成，
  不入仓（SPEC §6 边界：不污染主栈/仓库）。

# 离线迁移交付 SPEC（2026-10-04）

> 原始任务（用户原话要点）：公司服务器离线，唯一数据通道=资料库→广度追踪→
> GitHub广度情报 上传 tech-boundary-data-feed 每日增量包；明日把「代码（本仓最新
> commit）+镜像文件（向量空间、embedding 模型、镜像环境等）」上传公司 GitLab，
> 镜像放本仓 GitHub Releases；确保公司可正常运行。无人值守完成。
>
> 决策依据：decisions-grill.md（Codex 决策轮 4790-4909 行原文+逐条裁定）。

## 1. 交付物定义

### 1.1 代码（公司 GitLab 仓库部分）
- 来源：GitHub sbq9712/tech-boundary-db main 分支，最终 commit（含本次文档/部署
  脚本/模板更新；镜像内业务代码=终版 commit（api/agent 1019），二者差异仅文档/部署文件，见 §5 指纹矩阵）。
- 用户操作：GitHub 下载（zip 或 clone）→ 推公司 GitLab。仓库不含任何密钥/数据。

### 1.2 镜像（GitHub Release `server-20261004`，6 个）
| 镜像 | 来源 commit | 说明 |
|---|---|---|
| techdb-canonical-qa:1008 | qa-assets pin | bge-m3 固定 revision+基线向量/BM25+图谱+jieba |
| techdb-api:1019 | 终版 commit | 业务后端（alembic 0001→0033+分类/嵌入解耦） |
| techdb-readonly-agent:1019 | 终版 commit（重建） | 兼容 Agent（0801 树已过期） |
| techdb-web:1017 | 6307112 | 门户静态（含 breadth 数据内嵌副本） |
| postgres:16 | 官方 | 数据库 |
| alpine:3 | 官方 | db_backup/db_restore 操作增量卷依赖 |

打包：`docker save|gzip -1|split -b 1900m`；每镜像附 `.part.sha256`（分片）与
`.stream.sha256`（合并流）；Release 附总 SHA256SUMS。

### 1.3 数据资产（同一 Release）
| 资产 | 内容 | 体积 | 用途 |
|---|---|---|---|
| techdb_*.sql.gz | pg_dump（plain, gz） | 0.3M | 快照恢复主路径（db_restore.sh） |
| uploads_*.tar.gz | 上传对象（容器视角打包） | 69M | 同上 |
| qa_incremental_*.tar.gz | 增量向量/BM25 索引卷 | 9M | 同上 |
| graph-live.tar.gz | graph-export.json（45M 原文） | 8.7M | canonical-qa 图谱只读挂载 |
| document-models.tar.gz.part-* | docling 模型+bge-m3 tokenizer+HF 缓存 | 2.2G/2片 | api 文档摄取 bind-mount |
| breadth-data.tar.gz | processed+reports | 124M | api/web bind-mount |

敏感注记：快照含内网情报与口令哈希；仓库 PRIVATE；传完 GitLab 后建议删除 Release
资产或转归档（Release 描述与文档均注明）。.env/密钥任何情况下不入仓/入 Release。

### 1.4 文档（随代码 commit）
- 服务器迁移说明.md：更新 alembic head=0033、广度问答→门户问答、Release 入口
  （替代 docker-images 分支）、新增"既有 0801 服务器升级"与"快照恢复/全新起步"
  双路径、MTU=1500 默认（WSL=1410 注记）、POSTGRES_PASSWORD 恢复语义、QA 生成
  网关配置与降级行为、GitLab 大文件两种方案。
- 服务器迁移交付清单.md：指向 20261004 资产清单（指纹矩阵+装载命令+验收矩阵）。
- docs/qa-acceptance/offline-migration-20261004/：SPEC（本文件）、验收证据。

## 2. 公司侧安装流（文档主体，验收目标）
1. GitLab 取代码 + Release 资产；`sha256sum -c` 校验全部分片/流。
2. 装载镜像：`cat techdb-*.tar.gz.part-* | gunzip | docker load`（逐镜像）。
3. 解包数据资产：document-models→external-data/document-models；
   breadth-data→breadth/data/{processed,reports}；graph-live→
   services/canonical-qa/graph-live/graph-export.json；快照三件套→backup/。
4. `cp .env.example .env`：填 SECRET_KEY/POSTGRES_PASSWORD/
   TECHDB_INITIAL_ADMIN_PASSWORD/TECHDB_AGENT_API_KEY/TECHDB_QA_INDEX_TOKEN
   （随机值）；确认 MTU（默认 1500）；网关端点（问答生成/AI 分类用）。
5. 主路径：`scripts/db_restore.sh backup/techdb_*.sql.gz`（交互 yes）→ `./deploy.sh`。
   副路径（空白起步）：直接 `./deploy.sh`（空库自动迁移 0033，用户自建账号）。
6. 验收矩阵 §4 逐项通过。

## 3. 实现票（to-tickets 落地）
- T1 readonly-agent 重建（终版 commit，1018→1019 因 P0 修复升 tag）+重导出分片。
- T2 .env.example：默认 tag=交付集；MTU 1500；QA_LLM 网关注记；POSTGRES_PASSWORD 语义注记。
- T3 deploy.sh：QA 就绪断言补 incremental_index_ready；缺镜像文案指向 Release。
- T4 db_backup.sh：uploads/qa_incremental 经容器 tar（root 属主文件可读）+归档
  chmod 644 +alpine:3 预检；db_restore.sh 恢复侧核验：解包在宿主暂存目录
  --no-same-owner（恢复不受 root 属主影响）+alpine:3 预检（QA 卷恢复依赖）。
- T5 alpine:3 导出分片。
- T6 文档更新（§1.4 全部）。
- T7 离线模拟验收（§4 A1-A16）：独立项目 offsim20261004+internal 网络+分片 load
  起步；记录证据。
- T8 升级模拟：0801 镜像对空卷 alembic upgrade（以 0801 镜像内实际 head 为准，
  记录实测值，不作假设）→造数→dump→1019 栈恢复→自动迁移 0033→数据在。
- T9 快照恢复模拟：三件套恢复进离线栈（db_restore.sh，喂 yes）。
- T10 Release 发布（draft→资产上传→manifest.json+SHA256SUMS→指纹矩阵入
  notes→publish；manifest.json 含 schema 版本、镜像 tag/image id/digest、快照
  时间戳、数据资产 sha256、代码 commit，供公司侧机器可读校验）。
- T11 回归：全测试套件 + codex:review + 修复复测；push GitHub。

## 4. 离线验收矩阵（A1-A16）
- A1 平台/指纹：6 镜像 linux/amd64，image ID 与 Release notes 矩阵一致；分片
  sha256 全部通过。
- A2 往返：全部镜像从 Release 分片 load 成功（load 输出 tag 正确）。
- A3 禁网拉起：internal 网络（无外网路由）；五服务 Up，db/canonical-qa healthy。
- A4 alembic：全新卷启动后 `alembic current`=0033。
- A5 健康：/api/health ok；canonical /api/health 四项 ready 全 true 且
  total_records≈68523（基线）。
- A6 图谱：graph-export 挂载存在；QA 图谱接口非空（或 health 计数>0）。
- A7 鉴权与敏感路径：登录 ok；/.env /.git/config /backend/app/main.py /scripts/ →404。
- A8 taxonomy：登录后 /api/uploads/taxonomy 返回（叶子=125 类目录）。
- A9 feed 导入：上传真实 daily zip（tech-boundary-data-feed 最新包）→响应计数
  （inserted/updated/unchanged/deleted）→DB breadth_import_sessions 行在。
- A10 队列清零：breadth_index_tasks pending/failed=0（worker 用本地 bge-m3）。
- A11 三索引增长：canonical health incremental_records/documents 较导入前增长。
- A12 检索命中：canonical /api/search 召回当日导入记录（三路：向量/BM25/图谱）。
- A13 文档上传路径（P0 修复后语义）：门户上传一份小 PDF/DOCX→embedding ready
  →下载 SHA256 与库一致（验证 document-models 挂载）。分类与嵌入已解耦
  （upload_ingestion.py：分类异常只置 classification_status=failed，本地
  bge-m3 嵌入继续）：
  - A13a 无网关：分类 failed（classification_error 含原因）+ embedding ready +
    QA 可检索到该文档；随后配置网关后 POST classification/retry 可补齐分类。
  - A13b 有网关（offsim 模拟内网端点）：分类 classified + embedding ready。
- A14 重启恢复：`docker compose restart` 全栈→健康恢复、队列续跑无丢失。
- A15 备份/恢复闭环：离线栈上跑 db_backup.sh（验证 alpine:3 + 容器打包路径）→
  生成三件套→db_restore.sh 恢复→抽查数据一致。
- A16 网关不可用模式：模拟 TECHDB_AGENT_* 端点不可达→feed 导入与索引不受影响；
  QA 生成返回明确错误而非崩溃。
- A17 manifest.json：Release 内 manifest.json 可被 jq 解析；字段与 SHA256SUMS、
  指纹矩阵三方一致（tag/image id/资产 sha256）。
- A18 internal 网络双向断言：offsim 栈内任一容器对公网 DNS/路由不可达（如
  getent hosts github.com 失败或无默认路由），同时宿主可访问已发布端口
  （web/api/qa）——证明"离线不阻断服务"。
- A19 恢复语义：db_restore.sh 先停写服务再 DROP/恢复、uploads 旧目录保留为
  .pre-restore.*；恢复失败时不产生半写库（以事务 psql --single-transaction
  保证）。
- A20 代码一致性：公司 GitLab 侧 commit 与 GitHub main 一致（SHA 相同）；镜像内
  业务代码 commit 与 §5 指纹矩阵一致。
- A21 备份产物属主：离线栈 db_backup 产物在宿主以普通用户可读（644），sha256sum
  -c 可执行。

## 5. 指纹矩阵（Release notes 模板，T10 填实测值）
| 项 | 值 |
|---|---|
| 代码（镜像内业务代码） | <终版 commit（含 P0 修复）> |
| 交付 commit | <T6-T11 完成后的最终 commit> |
| techdb-canonical-qa:1008 | <image id> |
| techdb-api:1019 | <image id> |
| techdb-readonly-agent:1019 | <image id> |
| techdb-web:1017 | <image id> |
| postgres:16 | <image id> |
| alpine:3 | <image id> |
| 快照时间戳 | 20261004_214740 |
| graph-export | <sha256>（对应 data_version） |
| breadth data_version | <c5b416faba6e…（manifest meta）> |
| 资产 SHA256SUMS | 见 SHA256SUMS 资产 |

## 6. 边界与不做
- 不做镜像瘦身/重打 tag；不重建 qa 基线（保持已验收资产只读语义）。
- 不在 Release 放 .env/密钥；不删除任何既有数据/卷；不碰运行中的主栈
  （offsim 独立项目/卷/端口）。
- QA 生成侧在公司侧依赖内网网关（aigate.catl.com 或公司等效端点），本模拟仅验证
  「网关不可用时不影响导入/检索」与降级行为。
- 公司真实 0801 数据升级演练：无法在本机复现真实数据，按 R3 以本机 0801→0033
  模拟+文档强制「升级前先 db_backup」兜底。

## 7. 回滚（精确语义，不承诺自动回滚）
- 服务层：新栈异常→`docker compose down`（不 -v）→ .env 换回旧镜像 tag → up。
  仅换镜像，不涉及数据。
- 数据层：db_restore.sh 不是事务性"整体回滚"——数据库为单事务重建，uploads
  以 .pre-restore.* 旧目录保留、需手工确认后清理；QA 卷解包前不自动备份
  （升级/重恢复前必须先跑 db_backup.sh 三件套，作为数据层回滚依据）。
- 本机：offsim 项目 `docker compose -p offsim20261004 down -v` 清理，不影响主栈。

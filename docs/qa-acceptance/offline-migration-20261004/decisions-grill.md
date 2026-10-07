# 离线迁移交付（2026-10-04）决策清单（grill-with-docs 产物）

## 背景（原始任务原文要点）
- 目标：把 Tech boundary DB 整体迁移到公司服务器（离线，无互联网）。
- 公司服务器唯一数据通道：资料库→广度追踪→GitHub广度情报 上传
  https://github.com/sbq9712/tech-boundary-data-feed 每日增量包。
- 明日交付到公司 GitLab 两类内容：① 代码=本仓最新 commit；② 镜像文件
  （向量空间、embedding 模型、镜像环境等"具体还有啥我忘了，你都要考虑好"），
  放在本仓 GitHub Releases。
- 验收标准（用户原话）："确保最后把两方面东西放到公司 gitlab 并在公司服务器上
  运行后可以正常使用"。无人值守，不停下来问。

## 事实盘点（2026-10-04 调查）
- 代码：main@6307112 已推送 GitHub（权威 remote）。
- 线上已验收镜像（本机 docker）：techdb-canonical-qa:1007(7.55G，内含 bge-m3
  固定 revision + 基线向量/BM25 索引 + jieba + 图谱 + 记录资产)、
  techdb-api:1018(5.8G，源码与 6307112 校验一致)、techdb-readonly-agent:0801
  (5.8G，readonly_agent.py 与 HEAD 字节一致)、techdb-web:1016(575M，资产与
  HEAD 一致)、postgres:16(641M)。
- 数据量：pg_dump.gz≈262KB；uploads/=69M；qa_incremental 卷=14M；
  external-data/document-models=2.5G（bind-mount，.gitignore 排除，**必须随
  交付**，否则文档摄取 docling/bge-m3-tokenizer 缺模型）；
  breadth/data/processed+reports=362M（bind-mount，git 仅含 .gitkeep）。
- compose 全参数化：PG_VOLUME/QA_INCREMENTAL_VOLUME/UPLOAD_HOST_PATH/各端口
  均 env 可调 → 可拉起完全隔离的第二套栈做离线模拟。
- deploy.sh：校验 .env 密钥→目录→镜像在场→up -d --no-build→等待 db/qa 健康；
  api 容器 CMD= alembic upgrade head && uvicorn（自动迁移到 0033）。
- db_backup.sh 三件套：techdb_*.sql.gz + uploads_*.tar.gz + qa_incremental_*.tar.gz
  + sha256 清单；db_restore.sh 配套恢复。
- 仓库 sbq9712/tech-boundary-db 为 PRIVATE；feed 仓为 PUBLIC。
- gh 已登录 sbq9712（可创建 Release）；GitHub Release 单资产上限 2GiB。
- 既有文档：服务器迁移说明.md（head 写 0032 已过时；7.3.4 仍引用已下线的
  广度页问答，需改门户；"docker-images 分支"已不存在，需改 Release）。

## 决策清单（D=已倾向，待 Codex 逐题质询）
- D1 Release tag 命名：`server-20261004`；draft→资产齐→publish。
- D2 镜像集：5 镜像按已验收 tag 原样 docker save（不重打 tag/不瘦身）。
- D3 资产打包：`docker save|gzip -1|split -b 1900m`；交付 SHA256SUMS（分片
  与合并流双重）+ 装载命令；数据 tar 同法。
- D4 数据交付：快照（pg_dump 三件套）作为**可选**资产 + 文档两条路径
  （全新起步=默认；快照恢复=可选）。升级既有 0801 服务器路径也写明
  （换镜像+代码，卷不动，alembic 自动 0020→0033）。
- D5 git 外资产：document-models.tar.gz 与 breadth-data.tar.gz 必须随 Release。
- D6 .env.example 默认 tag 更新为交付 tag（1007/1018/0801/1016）+ deploy.sh
  fallback 同步改（fresh .env 开箱即用，不再回落 1001）。
- D7 文档更新：服务器迁移说明.md（0033/门户问答/Release 入口）+ 新
  交付清单（本次产物清单+校验步骤）。
- D8 离线验收（本机模拟，证明"公司可正常使用"）：
  a) 干净离线拉起：从 Release tar 重新 docker load → 独立 compose 项目
     （internal 网络、独立卷/端口、pull never）→ 验收清单
     （五服务健康/登录/taxonomy/feed zip 导入→队列清零→三索引增长→检索
     命中/敏感路径 404/上传对象落盘）；
  b) 升级模拟：0801 镜像建 0020 库→dump→用 1018 栈恢复→alembic 自动到
     0033→抽样数据在；
  c) 快照恢复模拟：db_restore.sh 三件套恢复到隔离栈。
- D9 readonly-agent 用 0801（已验证源码=HEAD）。
- D10 敏感边界：.env/密钥绝不入仓/入 Release；pg_dump 含内网情报与口令哈希
  → 仓库 PRIVATE 下随 Release 交付（用户明确经 GitHub 转运）；文档提醒
  现场改密与 SECRET_KEY。
- D11 增量索引卷：随快照三件套交付（14M，小）；升级场景公司已有卷则不覆盖。
- D12 postgres 交付形态：pg_dump 走既有 db_backup/db_restore 脚本（不搬卷 tar）。

## 风险清单（Codex 重点质询）
- R1 Release 资产总量 ~10G（压缩后）/上传时长；分片 2GiB 上限。
- R2 公司侧 GitLab 上传 10G 资产的可行性（用户自行操作，文档给 LFS/直传建议）。
- R3 0801→0033 迁移在真实公司数据上的兼容性（本机只能模拟）。
- R4 离线栈对 LLM 网关的依赖面（问答生成/上传 AI 分类需要内网网关；
  检索/导入/索引纯本地）。
- R5 web 镜像已内嵌 breadth 数据但 bind-mount 又覆盖——版本不一致可能
  （交付同源同版本，无差异）。
- R6 GitLab 代码导入后 .gitignore 资产缺失导致误 build web（deploy.sh 已有
  manifest 检查拦截）。

---

## Codex 决策轮结论（2026-10-04，原文日志：logs/codex_decisions_offline_migration.log 4790-4909 行）与我的独立裁定

| 项 | Codex 意见 | 裁定（含核实依据） |
|---|---|---|
| D1 | 同意 tag=server-20261004；描述须绑定源码 SHA/镜像ID/平台/资产SHA256；draft→publish | **采纳**。Release notes 附完整指纹矩阵。 |
| D2 | 部分反对：必须补 `alpine:3`（db_backup/restore 操作增量卷用） | **采纳（核实属实）**：scripts/db_backup.sh:71 与 db_restore.sh:157 均 `--entrypoint /bin/sh alpine:3`。镜像集=6：qa:1007/api:1018/**readonly-agent:1018（重建）**/web:1016/postgres:16/**alpine:3**。readonly-agent:0801 的 /app/app 已过期（缺 0033 期模块，已核实 diff），虽然当前运行正常（导入面窄），仍重建到 6307112 保持全镜像同源。 |
| D3 | 同意；建议数字后缀分片名+精确命令+分片恢复演练 | **采纳**：保持字母后缀（split 默认）但文档给精确 `cat … \| gunzip \| docker load`；往返演练纳入离线模拟（已做 web:1016 快速验证，全套在 D8 重做）。 |
| D4 | 快照应是主路径，全新起步为空白验收路径 | **采纳**：主路径=三件套快照恢复；副路径=全新起步（随附两种文档）。升级既有 0801 服务器单独成章（先备份再换镜像）。 |
| D5 | 反对资产集：必须补 graph-export.json；delivery-views/chatbot-package/knowledge-base 也要打包或校验 | **部分采纳**：graph-export.json 已补（graph-live.tar.gz，核实 compose:49 只读挂载）。KB/chatbot/delivery-views 三目录本机为空目录（du=0），compose 挂载可缺省创建；在文档中说明"如现场有数据自行放置"，不打包空壳。 |
| D6 | .env.example/deploy.sh 改默认 tag 会造成镜像与交付 commit 脱节 | **采纳其风险，裁定不重建镜像**：已核实 backend/web Dockerfile 均不 COPY deploy.sh/.env.example/docs——文档/模板改动不影响镜像内容；Release 指纹矩阵写明「镜像内代码=6307112；交付 commit=后续（仅文档/部署脚本/模板差异）」。默认 tag 同步为交付集（含 readonly-agent 1018）。 |
| D7 | 同意 | 采纳，按计划更新 0033/门户问答/Release 入口。 |
| D8 | 清单不充分：补平台校验/alpine/图谱挂载/数据版本一致/网关两种模式/文档上传/重启恢复/权限/回滚演练 | **采纳**（见 SPEC 验收矩阵 A1-A16）。网关不可用模式：离线模拟天然覆盖（无外网）；QA 生成在公司侧由内网网关承担，文档写明配置要求与降级行为。 |
| D9 | readonly-agent 应随 6307112 重建 | **采纳**（见 D2 裁定），重建 tag=1018 并纳入验收。 |
| D10 | 快照加密后随 Release | **不采纳加密，采纳安全注记**：仓库为 PRIVATE、数据本为公司情报、用户明晨需直接上传公司 GitLab；加密引入第二通道传口令，违背"无人值守直接可用"。Release 描述+文档注明：资产含内网数据，仅限本人下载，传完 GitLab 后建议删除 Release 资产/或转私有归档。 |
| D11/D12 | 同意 | 采纳。 |
| R1 上传时长 | 10G 可行 | 实测压缩后镜像 3.4G+模型 2.2G+其余 ~0.3G ≈ 5.9G，压力更小。 |
| R2 GitLab 大文件 | 确认 LFS/Release 能力或安全网关 | 写入文档（给 LFS 与直传两种方案+分片约束）。 |
| R3 0801→0033 真实数据 | 先备份、演练 | 本机做「0801 建库→dump→1018 恢复→0033」升级模拟；真实公司数据升级时先 db_backup 三件套（文档强制）。 |
| R4 LLM 依赖 | 生成需网关；检索/导入/索引本地 | 已核实 feed 导入链路（github_import→队列→canonical-qa 写索引）不需外网/LLM；.env 默认端点改公司网关说明（QA_LLM_BASE_URL 公网 Z.AI 默认必须覆盖——写入 .env.example 注释与部署文档）。 |
| R5 web 内嵌 vs 挂载 | 版本一致性 | 同源打包（breadth-data.tar.gz 与 web:1016 构建输入同版本），文档注明。 |
| R6 误 build | deploy.sh 拦截 | 已有 manifest 检查；再补：镜像缺失时的报错文案指向 Release（替换 docker-images 分支说法）。 |
| MTU | 公司服务器默认应为 1500 | **采纳（核实属实）**：.env.example TECHDB_DOCKER_MTU=1410 是 WSL 场景；默认改 1500+注释（WSL 才用 1410）。 |
| deploy.sh QA 就绪断言 | 补 incremental_index_ready | **采纳**：与容器 healthcheck 对齐。 |
| POSTGRES_PASSWORD 恢复语义 | 不会自动改既有库密码 | 文档写明（升级场景沿用原密码/改密流程）。 |

## 拍板汇总（变更点）
1. 镜像集 6 个（新增 alpine:3；readonly-agent 重建为 1018）。
2. 数据资产 6 件：三件套快照（主路径）+ graph-live + document-models + breadth-data。
3. .env.example：默认 tag=交付集；TECHDB_DOCKER_MTU 默认 1500（注释 WSL=1410）；补
   TECHDB_QA_LLM_BASE_URL 等网关覆盖注记。
4. deploy.sh：QA 就绪断言补 incremental_index_ready；缺镜像报错指向 Release。
5. db_backup.sh：uploads/qa_incremental 改经容器打包（root 属主可读，公司侧同样适用）。
6. 文档：服务器迁移说明.md 全面更新（0033、门户问答、Release、升级路径、MTU、密码语义、
   网关与降级、GitLab 大文件）；新增交付清单（指纹矩阵+资产+装载命令+验收矩阵）。
7. 离线模拟（D8）：独立项目+internal 网络+从分片 load 起步，全验收矩阵 A1-A16；
   含 0801→0033 升级模拟与三件套快照恢复模拟。

## ⑤ 终稿质询处置（codex_spec_final_review.log，2026-10-07）
> Codex 审的是质询时的树；部分意见与本会话已完成的修复重叠，逐条以现状核实。

| 意见 | 级别 | 裁定与证据 |
|---|---|---|
| A13 无网关不可能 embedding ready（分类异常进统一失败分支） | P0 | **属实，已代码修复**：`upload_ingestion.py` 分类调用改为 try/except——异常只置 `classification_status=failed`（source=system，error 含原因，primary_category=未分类），本地 bge-m3 嵌入继续。回归测试 `test_classification_gateway_failure_does_not_block_local_embedding`（红=旧 api:1018 镜像容器内 FAIL，绿=修复后宿主 PASS）。事后补齐路径已存在：`POST /uploads/{id}/classification/retry`（重置整条流水线）与 `PUT /uploads/{id}/classification` 人工分类。A13 拆 A13a（无网关）/A13b（模拟内网网关）。 |
| compose 未透传 TECHDB_QA_LLM_BASE_URL，公司网关配置不生效 | P1 | **已完成于质询前**（Codex 审旧树）：docker-compose.yml:43 已透传；qa:1008 config.py 空串回落（`_raw_base or 默认`）——qa:1008 正是为此而建（镜像不含 compose/文档，无需再重建）。 |
| db_restore.sh 宿主直读 root 属主归档会失败 | P1 | **反驳（证据）+部分采纳**：容器 tar 产物默认 umask 022=644，宿主普通用户可读（已实测备份三件套在宿主 sha256sum 通过）；真正 root 属主问题只在"读 uploads 目录内容"（备份侧），已改容器打包。仍采纳保险：备份脚本容器打包后 `chmod 644`（显式）+alpine:3 预检（backup/restore 双侧）。A21 验收断言"宿主可读可校验"。 |
| 恢复脚本回滚语义被 SPEC 夸大 | P1 | **采纳**：SPEC §7 重写为精确语义（数据库单事务；uploads .pre-restore 保留需手工清理；QA 卷解包前不自动备份→升级/重恢复前强制 db_backup；不承诺自动回滚）。A19 验收断言。 |
| Release 缺机器可读 manifest.json；.part.sha256 冗余 | P1 | **采纳**：T10 产出 manifest.json（schema 版本/tag/image id/快照时间戳/资产 sha256/代码 commit）+统一 SHA256SUMS；A17 验收三方一致。.part.sha256 保留本地目录（无害），Release 以 SHA256SUMS 为准。 |
| T7 internal 网络只声明未断言 | P1 | **采纳**：A18 双向断言（容器内公网不可达 + 宿主可访问发布端口）。 |
| T8 "→0020" 属猜测 | P1 | **采纳**：SPEC 改为"以 0801 镜像内实际 head 为准，记录实测值"。 |
| 快照资产命名/文档一致性（two-machine GitLab SHA 等） | P1 | **采纳并入 A20**：交付清单写明 GitHub commit=GitLab commit 同 SHA 校验命令；A17 manifest 含双方字段。 |
| Q8 分片校验统一 | Q | 采纳（同 manifest 行）。 |
| Q9 deploy.sh 只做占位校验 | Q | 接受现状；A16 断言网关不可用降级行为，公司侧文档写明网关可达性自检命令。 |
| Q10 .gitignore backup/ | Q | 已有（.gitignore:52），无需重复。 |

### 追加拍板（变更点补充）
8. 分类/嵌入解耦修复（P0）随交付 commit 入库；api:1018 镜像含该修复需在 T11 重建为
   1019（业务代码变更不可与 1018 混 tag）。readonly-agent 同源重建 1019；qa:1008 不受
   影响（不涉 upload_ingestion）。web 不受影响。
9. db_backup.sh 容器打包后 chmod 644 + alpine:3 预检；db_restore.sh alpine:3 预检。
10. Release 附 manifest.json（机器可读）+SHA256SUMS（唯一权威校验清单）。

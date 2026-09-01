# 技术边界数据库 NEXT_SESSION

项目: 技术边界数据库
用途: 新 session 快速接续 / 当前阶段 handoff
更新: 2026-09-01
状态: GitHub 协同已开通（main 与 #DEV 同步，sbq9712 已授权）；0801 + 0804 已交付服务器；0807+0818 已提交本地并推送 GitHub，待下次发版上服务器

## 1. 当前状态

活动开发版：`#DEV`（固定名称，不按日期命名）

- 路径：`D:\##EDMUNDS\技术数据库\#DEV`
- 当前分支：`main`
- 最新 commit：`c27edca docs(pilot): record review-UI gap from user feedback`（2026-08-19）
- 最新稳定 tag：`v260801.2`（2026-08-03；另存在历史标签 `v260723`、`v260801.0`、`v260801.1` 和早期别名标签 `v0801`）。0801 之后 main 上已有 16 个提交（0804 补丁、0807 加固、0818 判断树试点），尚未打新 tag。
- Git 跟踪：228 个文件，工作树 clean
- remote：`https://github.com/EDMUNDSdaONE/tech-boundary-db`（私有）。2026-08-31 已推送 main + 全部 5 个 tags，与本地 `#DEV` 完全一致。
- 协作：协作者 `sbq9712`（write 权限，2026-09-01 生效）。同事 clone 得到的是 main 活动版（不是最新 tag 对应的 0801 快照）；大数据资产不入仓，按仓内 `external-data/README.md` 契约从 `支撑资料/`、`06_交付/` 本地补齐。
- 本机 gh CLI：`C:\Program Files\GitHub CLI`（bash 中需手动加 PATH），已登录 `EDMUNDSdaONE`。仓库提交身份：`EDMUNDSdaONE <118644341+EDMUNDSdaONE@users.noreply.github.com>`（repo-local）。

冻结稳定版目录（只读保留）：`v260518.0`、`v260623.0`、`v260716.0`。
注：`v260629.0` 目录已不存在（内容已合入 v260723），历史记录中有此说明，勿在脚本或文档中引用该目录。

## 2. 版本命名约定（重要）

- 开发版固定名称 `#DEV`，不按日期命名。
- 日期命名的 `vYYMMDD.N` 目录均为冻结稳定版。
- 新里程碑：在 `#DEV` 内打 annotated tag，push 到 GitHub remote，可选复制一份冻结目录。

## 3. 0801 → 0804 → 0807 关键变更

### v260801.x（0801 稳定版，已交付服务器）

- 上传文件按 SHA-256 落盘到服务器持久目录，数据库登记对象键、分类状态和校验信息。
- 新上传统一使用广度追踪 77 项输出（75 项业务分类 + 未分类/不相关），旧行业图景冻结备份。
- 密级统一为公开/内部/管理员；AI 只自动输出公开和内部。
- 门户"与知识库互动"切换到 `sbq9712/tech-db` canonical QA 检索契约；旧用户会话经迁移 0019 清空。
- Compose 固定 `techdb-api:0801`、`techdb-canonical-qa:0801`、`techdb-readonly-agent:0801`、`techdb-web:0801` 和 `postgres:16`。
- Git 当前树已移除知识库正文跟踪，仅保留外置数据挂载契约。

### 0804 问答补丁（已交付服务器，2026-08-04）

- 轻量补丁形式：服务器本地基于 0801 镜像构建，payload 四文件 + 三份 Dockerfile.patch + 服务器专用 Compose。
- 运行参数：超时 180s、检索 30000 字、输出 10000 tokens；canonical-qa 宿主机回环端口 9003。
- 交付位置：`06_交付/0804/0804-qa-patch`（tar.gz + 解包目录 + zip），真实 `.env` 单独存放于 `06_交付/0804/techdb-server.env`。
- **2026-08-17 起这些改动已提交进 `#DEV` Git**（commit afb4b3e 等），服务器运行状态与本仓 `main` 一致。

### 0807 分类健壮化（2026-08-17 已提交，尚未部署服务器）

- 分类输入改为整篇代表性采样（头/中/尾 4:3:3，预算 4 万字）。
- 目录命中三级匹配：精确 → 归一化 → difflib ≥0.9；失败写 `classification_error`。
- AI 调用指数退避重试（仅瞬时错误）；ADR-0002 记录放弃 embedding 分类的决定。
- 备份/恢复单元补齐 QA 增量索引卷（`techdb_qa_incremental_0801`）。
- `.gitattributes` 全源码钉 LF，防止 autocrlf 破坏交付校验。

## 4. 支撑资料

完整支撑资料保存在：`D:\##EDMUNDS\技术数据库\支撑资料\`

包括：知识库快照、交付视图、Chatbot 索引、广度追踪数据、清理前数据库基线。

逐文件 SHA-256 清单：`支撑资料/support-manifest.json` 和 `支撑资料/support-files.sha256`。

上游 canonical QA 源码仓：`D:\##EDMUNDS\技术数据库\upstream\tech-db-20260803`（pin `fdffba1`，验证过是其祖先）。其余 upstream 子目录为临时拷贝/失败克隆，清理决定见 00_控制面。

## 5. 验证状态（2026-08-17 本机实跑）

- `python -m compileall`：通过。
- pytest：`test_upload_ingestion` + `test_agent_service` 32 项全过；除环境依赖套件外 59 项全过。
- `test_api_endpoints`（33 错）需要本机 PostgreSQL、`test_portal_ui_contract`（7 败）需要 Docker web 容器：本机 Docker Desktop 未运行所致，非代码问题；与历史记录"84 passed"的差异即这两套。
- 0804 payload 与 `#DEV` 提交内容逐字节一致（md5 核对）。
- 备份/恢复脚本 `bash -n` 通过；**Docker 环境实测待服务器端执行**（本机无 Docker 运行）。

## 6. 下一步

1. **Git 历史已 rewrite（2026-08-17）**：`external-data/knowledge-base` 的 ~60 个 blob 已从全部历史清除。代价：所有旧 commit hash 失效；rewrite 前的 `.git` 完整备份在 `99_归档/DEV-git-pre-rewrite-20260817.git`。**公司服务器上 `06_交付/0801/tech-db-0801-main/.git` 仍是旧历史**，下次向服务器交付代码包时必须整体替换该目录（不要在其上 git pull），废弃副本按凭据管理流程删除。**GitHub 仓库已含 rewrite 后历史**，无需再处理。
2. 在公司服务器更新代码包（0807 分类健壮化 + 备份修复），部署时打新 tag；顺手在服务器实测新版 `db_backup.sh`。
3. 生产凭据治理：`06_交付/0804/techdb-server.env` 明文凭据单独传输，严禁打包进任何交付 zip/tar；`#DEV/.env.local` 中 xiaowang886 key 待确认是否仍需要、能否轮换删除；`ATSC1231/ATSC001` 弱口令模式待换强密码。
4. **深度调研重构（2026-08-18 起，进行中）**：方法论 11 份 ADR（`#DEV/docs/adr/0003-0011`）已定案；SOFC+核聚变两个竖井已建（`#DEV/pilot/`，判断树+信号+观测+HTML 认知面板 v4）；P0 待核实项已联网核实一轮。**待用户审**：两份 fusion-panel/panel 的待审队列（epistemic 改判、行业判断时间线句、Helion D-T 扩大氚卡点、约束性卡点确认）。**下一步**：竖井阶段 2（生成式调研，可用新装的 hv-analysis skill）、IT 白名单清单整理（ADR-0010 附注）。
5. 外部知识库、delivery views 和旧 chatbot 包继续通过服务器绝对路径挂载，不放入普通 Git。
6. **协同开发约定（2026-09-01 与 sbq9712 起两人协作）**：建议 feature 分支 + PR 合入 main；如需强制，可在 GitHub 上配 main 分支保护（禁止直接 push、要求 review）。生产凭据、`.env`、大数据资产严禁提交入仓（`.gitignore` 已挡，评审时注意勿用 `git add -f`）。

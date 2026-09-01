# 协作约定（CONTRIBUTING）

适用对象：本仓库全部开发者。基础背景（版本体系、tag 约定）见 [版本索引.md](./版本索引.md) 与 [技术边界数据库_NEXT_SESSION.md](./技术边界数据库_NEXT_SESSION.md)。

## 1. 权限与协作方式

- 所有协作者拥有 **write** 权限：可以直接 push 功能分支、创建/评论/合并 PR、管理 issue。
- `main` 分支是活动开发线：**小改动（docs/fix）可直接 push；功能性改动走 feature 分支 + PR**，让另一人有机会 review。
- 禁止 `git push --force` 到 `main`；禁止绕过历史重写。

## 2. 分支与 commit

- 功能分支命名：`feat/*`、`fix/*`、`docs/*`、`chore/*`。
- commit 格式：`type(scope): description [TASK-TECHDB-XXX]`（有任务号必带）。
- 每个 TASK 至少一个 commit；一次 push 前确保 `git status` 干净、不留调试代码。

## 3. 提交前自检

1. `python -m compileall -q backend/app backend/scripts scripts`
2. `cd backend && python -m pytest -q`（环境依赖无法跑的套件在 commit 信息或 PR 里注明，不得写成已通过）
3. `git status --short` 确认无误入文件

## 4. 仓库边界（重要）

**严禁入库**（`.gitignore` 已挡，也不要 `git add -f` 绕过）：

- `.env`、`.env.local`、任何 API key / 密码 / 私钥
- PostgreSQL dump、上传文件本体、PDF/专利 ZIP
- 知识库全文、大型 JSONL/CSV/SQLite 索引、向量索引
- 虚拟环境、缓存、构建产物、Docker 卷数据

外部支撑数据按 `external-data/README.md` 的契约本地补齐，来源为项目工作区 `支撑资料/` 与 `06_交付/`。

**提交他人信息前先自查**：commit 邮箱请使用各自 GitHub 账号的 noreply 邮箱（`<id>+<username>@users.noreply.github.com`），不要用公司内网邮箱直推。

## 5. 版本与发布

- 里程碑发布：从 `main` 打 annotated tag `vYYMMDD.N` 并 push tag；发布验收清单见工作区《版本管理规范》第 6 节。
- tag 即冻结点，不打在 feature 分支上。
- 发版后更新 `docs/版本索引.md` 的 tag 对照表。

## 6. 约定俗成

- 文档以中文为主，术语遵循 `CONTEXT.md` 的领域语言（"文件落盘"、"资料入库"等有严格定义，勿混用）。
- 架构决策走 ADR（`docs/adr/`），编号递增，定了就不改内容、只加新 ADR 推翻。
- 拿不准的改动先开 issue 或直接问，别攒大 PR。

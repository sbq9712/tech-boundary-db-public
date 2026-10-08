# Codex Review：离线交付 server-20261004 最终评审（无人值守轮）

仓库：tech-boundary-db（当前目录，HEAD=9908ce0，与 origin/main 一致）。
背景：整套系统将迁移到公司离线服务器（唯一数据通道=GitHub Release 资产 + GitLab 代码镜像）。
请实际审查以下 8 个 commit（用 `git show <sha>` / `git log 091a1f8^..9908ce0 --stat` 自行读取）：

- 091a1f8 fix(offline): 分类网关不可达不再阻塞本地嵌入（P0 修复）
- 47e757b feat(deploy): 离线交付集 server-20261004 部署默认值（T2+T3）
- 685b5ea fix(backup): uploads/QA 卷备份经容器打包 + alpine:3 预检（T4）
- 3fa2082 docs(offline): 迁移 SPEC 定稿 + 终稿质询逐条处置
- e4eeb6a docs(migration): 离线交付 server-20261004 全面更新
- b94e4cd fix(web): nginx upstream 动态重解析——api 重启不再全量 502
- 8ce770c docs(offline): T7-T9 演练证据 + web 1017 全仓同步
- 9908ce0 chore(gitignore): 忽略管线运行时轮换备份目录

重点核查（按优先级）：
1. backend/app/services/upload_ingestion.py：分类网关异常分支是否遗漏 commit/rollback/幂等/时间戳；嵌入失败路径是否被改变；对照 backend/tests/test_document_ingestion.py 的 test_classification_gateway_failure_does_not_block_local_embedding 是否真实覆盖该分支（mock 是否绕过了被测代码）。
2. nginx.conf：resolver+变量 proxy_pass 改法是否破坏 SSE（proxy_buffering/proxy_read_timeout 是否保留在正确 location）、是否影响其他 upstream；web:1017 重建后是否还有遗漏的静态 upstream 引用。
3. deploy.sh + docker-compose.yml：默认 tag（qa=1008/api=1019/agent=1019/web=1017）与 QA 就绪断言（incremental_index_ready 且非 corrupt）逻辑正确性；缺镜像提示与 Release 分片装载命令一致性。
4. scripts/db_backup.sh / db_restore.sh：容器打包（tar chmod 644）是否会在 .incoming 排除/卷挂载/文件名含空格等边缘场景失败；alpine:3 预检两侧是否齐全。
5. backend/tests/test_deploy_image_contract.py：断言与脚本实际文本是否同步（有无测了不存在的行为）。
6. 文档（SPEC/decisions-grill/evidence-offsim/服务器迁移说明.md/服务器迁移交付清单.md）：tag 矩阵、回滚语义、A13a/A13b 拆分是否与代码一致，有无自相矛盾。
7. .gitignore 新条目是否会误忽略需要提交的文件。

硬性要求：每条意见必须给出 文件:行号 与可复现依据；不确定的标注 [推测]。
输出格式：编号列表，每条 `[P0|P1|P2|P3] 文件:行 - 问题 - 建议`；无问题输出 `NO FINDINGS`。

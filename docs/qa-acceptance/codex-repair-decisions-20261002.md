# Codex 决策轮原文（2026-10-02，repair 工单 D1-D12）

> 调用方式：codex exec（read-only sandbox），输入 = /tmp/repair/grill-decisions.md
> （D1-D12 决策问题 + 现场勘察事实 F1-F12）。以下为 Codex 回复正文；其执行日志中
> 含本地 .env 读取痕迹，已整体剥离（密钥绝不入库）。问题原文见
> docs/qa-acceptance/spec-repair-20261002.md 引用与上文章节。

---

逐题结论如下；其中 D1、D2、D4、D6 我会加实现级修正。

- **D1 接受 A + dead-letter，但不要叫 LWW**：重复记录没有可靠时间戳，应定义为“发布视图规范化 winner”：排序后的文件路径 + 行号取最后一条，fresh/changed/keep/mutate/baseline 全部用同一 winner map。基线应在 winner 去重后的记录集上构造，避免 rec0/rec1 分裂。dead-letter 不推进基线、只停止重试，语义可接受；但必须落 `attempts/first_seen/last_seen/reason/op/winner_digest`，winner digest 变化或 `--rearm-dead-letter` 才恢复，并在健康/日志中可见，不能只是静默 exit 0。

- **D2 接受，重放条件建议改掉 `updated_at < reset_at`**：`corrupt` 状态和 healthcheck 断言是对的；文件存在但损坏 unhealthy，文件不存在 healthy。损坏时应把 reset epoch/id 持久到 canonical 侧，否则重启后信号消失。API 侧不要只重放旧时间任务：canonical 清空后、API 发现前完成的 done upsert 会漏掉。应持久保存“已确认的 reset epoch”，每次发现新 epoch 时一次性把 `done + op=upsert` 任务条件性重置 pending，幂等重放；delete 不重放，依赖 canonical 墓碑。这比对比计数更可测，也能避免部分损坏被计数误判。

- **D3 接受摘要级渲染**：canonical `claim_check` 是 compact 契约，没有逐 claim 明细，门户不应伪造粒度。渲染四态徽章、边界条、总数/支持数/重大不支持数和安全命中即可；`verification` 有值才显示摘要。所有字段缺失时整块降级。

- **D4 接受删死分支，但“列出 unsupported_major_claims”当前不可行**：canonical compact 只给 `unsupported_major_claims` 数量，没有明细数组，不能在抽屉里列出内容。应显示计数；若未来契约新增数组，再按数组渲染。删除 `claims`、`reference_cards`、citation 内 `grounding_status/supports_claim_ids/source_role/快照漂移` 等不可达分支，用新 `claim_check/evidence/retrieval_trace` 补真实内容。

- **D5 接受共享模块，但不建议同一文件同时做 ES module 和 classic script**：`app.js` 和 `breadth/qa.js` 都是普通 `<script>`，HTML 没有 `type=module`。建议 `safe_url.js` 用 IIFE 挂 `window.TechDBSafeUrl`，并加 CommonJS 导出供 Node 测试；HTML 中先加载它，再加载两个消费者。qa.js 内保留 `_qaSafeUrl/_qaSafeHref` 别名以兼容现有测试。

- **D6 接受 A+B，但要承认会破坏当前本地写入路径**：我确认 `.env`/`.env.local` 当前都是占位符，所以 A 上线即会让空/占位令牌的写请求失败。安全语义应取“未配置或占位符等同未配置”，canonical 对 upsert/delete/record-mutate 返回 503/403 明确错误；只读诊断端点也不宜完全裸奔。发布步骤必须先生成真实随机 token、写入共享 `.env`、再重建/重启 canonical 和 api；api 启动 warning 保留。

- **D7 接受**：`SuccessExitStatus=3` 是正确处理，exit 3 表示部分成功且下轮续跑；真实失败仍走 Failed/OnFailure。文档同时写清 0/3/其他退出码，避免告警语义漂移。

- **D8 接受改默认 8767**：容器内 canonical 仍是 8765，只改宿主映射默认，不影响 compose 网络内 `http://canonical-qa:8765`。已显式设置 `TECHDB_QA_PORT` 的部署不受影响。顺手清理 `.env` 里 8765/8767 重复行，避免后续误读。

- **D9 接受，写入 `pipeline/.env` 可行**：该路径在 vendored 引擎向上查找范围内，也满足“非 vendored、可 0600”的要求。实现时不要覆盖既有 `pipeline/.env`，应合并/原子写；若 vendored `ENGINE_DIR/.env` 已存在则迁移。`.gitignore` 规则要实测，避免删掉精确规则后因宽匹配产生误判。

- **D10 接受，本机演练可行**：走 `/api/uploads(section=breadth, source=github)` 是正确验收入口。运行时读取管理员凭据和 JWT，不回显；证据保存导入计数、队列状态、canonical health 索引数、QA 召回摘录和红acted 日志。建议演练前记录 DB/QA volume 快照或至少完整前后状态，便于失败归因。

- **D11 接受做逐文件列**：`upCfg` 已有逐文件结构，改动小且后端本来就按文件持久化 `sync_breadth`。默认保持否，不引入“半选/整批覆盖”的新状态；保留现有整批行为仅在旧配置兼容层中处理。

- **D12 接受 failed 语义**：`rec.title` 在导入链必填，且队列 `_upsert_payload` 会把 title 加入 text，所以正常记录不会生成空 chunks；canonical 端也本就拒绝空 chunk。空 chunks 应从 `_execute` 抛错并经现有 retry/failed 机制标记 `last_error="empty payload"`。删除分支和“记录已不存在视为 done”的语义都保持独立，不受影响。

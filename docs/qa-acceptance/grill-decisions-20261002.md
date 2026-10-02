# 三仓库审计修复工单（T1-T12）——实现前决策清单（grill）

仓库：~/tech-boundary-db（GitHub sbq9712/tech-boundary-db，main 权威）。审计报告：docs/qa-acceptance/three-repo-audit-20261002.md；修复工单：docs/qa-acceptance/repair-prompt-20261002.md（T1-T12，含验收标准，视为需求原文）。

已完成的现场勘察（关键事实，供你决策参考）：
- F1 G9 根因已实测定位：runtime/qa-index-sync/state.json 中卡死键 8c218bc2…（update op）对应发布视图两条同 (t,d,u) 记录：rec0（富化版，digest 1dab6f79≠基线）与 rec1（贫瘠版，digest aca48fc7==基线）。scripts/sync_qa_index.py 的 changed 选择"首个差异行"（rec0），而 kh_to_rec/new_key_hashes 基线用"最后一条"（rec1，LWW）→ keep_content_sha(rec1)≠批次 csha(rec0) → 确认永远失败。今日 13:06 实跑复现（mutate pending + 批次 ready 但仍 deferred）。
- F2 canonical /api/health 已含 incremental_index_ready/_incremental_index.loaded，但 incremental_index.py load() 损坏路径置 loaded=True 后清空数组 → health 恒 true（G1 洞）。compose healthcheck 只断言 vector/bm25/mapping。
- F3 canonical done 载荷实有字段：answer_status/stop_reason/knowledge_boundary/claim_check(compact: claims_total,claims_supported,unsupported_major_claims,verification,numeric,grounding,repair,coverage_gate,refusal,boundary_message,safety_hits)/safety_hits/evidence/retrieval_trace。无 claims 明细/无 evidence_summary/无 reference_cards（build_evidence_summary 存在但从未接线）。citations 无 grounding_status/supports_claim_ids。
- F4 breadth/qa.js 渲染层读 msg.claims/evidence_summary/reference_cards（永不填充→永不渲染）+ 已读 answer_status/knowledge_boundary/safety_hits/evidence/retrieval_trace 但后三者只存不渲染。
- F5 门户 app.js done 处理（:1491）丢 answer_status/knowledge_boundary/claim_check/safety_hits；app.js inlineMd(:70) 链接未做 scheme 白名单（escapeHtml 存在 :1639）；breadth/qa.js 已有 _qaSafeUrl/_qaSafeHref(:1081-1094)。
- F6 breadth_index_queue._execute upsert 分支 `if not payload["chunks"]: return`（静默成功）。
- F7 IndexTask 有 updated_at（完成时间可用）；api main.py lifespan 起 worker（默认开）；无 /api/index/stats，用 /api/health。
- F8 引擎 load_env 从引擎模块目录向上 4 层找 .env；engine_triage._ensure_llm_env_file 写 ENGINE_DIR/.env（vendored 内）；.gitignore 已含 pipeline/triage_engine/.env 与 .env。
- F9 backend/tests/test_feed_v2_import_and_queue.py:31 parents[2]/scripts 在容器布局（/app/tests）下解析到 / 失败 → pytest 收集错误。
- F10 systemd user unit breadth-pipeline.service（Type=oneshot）无 SuccessExitStatus；exit 3=部分成功按设计，但显示 Failed。
- F11 文档：服务器迁移说明.md（6 章）、DEPLOY.md、服务器迁移交付清单.md 均无"离线每日更新"章；README.md:16 引用不存在 scripts/auto_update_takeover.sh；services/canonical-qa/README.md:66/76/84 指向 /home/rhett/tech-db-fresh。
- F12 docker-compose.yml canonical-qa 端口 "${TECHDB_QA_BIND:-127.0.0.1}:${TECHDB_QA_PORT:-8765}:8765"；本机 override 用 8767。

## 决策问题（请逐题给建议 + 理由；P0=分歧需收敛，P1=取稳）

D1 (P0) G9 修复方案：A=差异评估统一到单一 LWW winner map（fresh/changed/keep/基线全用同一条记录），卡死键下轮即稳（零推送零延迟）；B=仅修 keep=record_digest(changed[kh]) 并把确认后基线写成 keep（会留下 rec0/rec1 交替重推，每轮 1 次幂等推送直到源头去重）。我倾向 A。另配 dead-letter 安全网：deferred 键累计 attempts（落 state），>6 次自动转 dead_letter.json（含键/op/首次末次时间/原因/当时的 winner digest），后续轮次不再重试该键（管线恢复 exit 0）；当该键 winner digest 变化（新内容）或 --rearm-dead-letter 时自动恢复。是否同意？dead-letter 不推进基线（不谎报已同步），只停止重试——语义可接受吗？

D2 (P0) T3 incremental 损坏检测：A=incremental_index.load() 损坏时置 self.corrupt=True（新状态，health 暴露 incremental_index_ready = loaded and not corrupt；文件存在但损坏→unhealthy；文件不存在→healthy）+ health 暴露 incremental_reset_at（损坏清空时间戳）；B=不区分损坏与不存在（都 healthy）。compose healthcheck 增断言 incremental_index_ready。api 侧恢复：worker 线程内每小时 GET /api/health，发现 incremental_reset_at 变新 → 把 updated_at < reset_at 且 status=done 的 upsert 任务重置 pending 重放（幂等）。删除任务不重放（墓碑持久、独立存储）。是否同意？有无更简单且可测的方案？

D3 (P1) T5 门户渲染：在 assistantMsg.extra 增加 answer_status/knowledge_boundary/claim_check/safety_hits/verification 摘要，渲染：状态徽章（四态 SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED/UNVERIFIED 中文映射）+ 边界提示条 + 声明核验摘要行（claims_total/supported/unsupported_major_claims）+ 安全命中提示。不做逐 claim 卡片（门户无 claims 明细契约，避免伪造粒度）。字段缺失优雅降级。是否同意"摘要级"而非"逐条卡片"？

D4 (P1) T6 广度页对齐：保留 answer_status 徽章；新增 knowledge_boundary 提示条、safety_hits 提示、从 claim_check 派生 evidence_summary（requirements_total=claims_total, requirements_supported=claims_supported）喂给现有摘要行；删除永不激活的 claims 明细卡与 reference_cards 渲染分支（含 citations 内 grounding 徽章/source_role/快照漂移——canonical citations 无这些字段）；unsupported_major_claims 在抽屉内列出（有数据才显示）。是否同意删死分支？（git 历史可找回）

D5 (P1) T7 共享安全 URL 模块：新建 web/assets/lib/safe_url.js（ES module，导出 qaSafeUrl/qaSafeHref），breadth/qa.js 与 app.js 引用（qa.js 现有 _qaSafeUrl/_qaSafeHref 改为 re-export 或内部别名保持测试钩子兼容——tests/js/test_qa_sse_parser.mjs 断言 _qaSafeUrl/_qaSafeHref 存在）。app.js 是传统脚本（非 module）？需确认加载方式：若 index.html 未用 type=module，则用普通 IIFE 全局（window.TechDBSafeUrl）双注册。倾向：safe_url.js 定义纯函数并挂 window + UMD-ish，qa.js/app.js 均可用，测试直接 import 文件。是否同意？

D6 (P1) T8 token：A=canonical-qa _check_index_token 在配置值为占位符（含空）时放行只读、但写端点对占位符/空令牌返回 503 明确报错（避免未配置时静默裸奔 + 不破坏现有本地环境）；B=仅 api 启动时对占位符打 WARNING 日志。我倾向 A+B 都做（api 侧 warning + 服务端拒绝占位符写）。风险：现有本地 .env 若未配 token，写路径会断——需检查本机实际配置后再定（若本机已配则 A 安全）。你建议？

D7 (P1) T9.3 systemd：给 breadth-pipeline.service 加 SuccessExitStatus=3 + 注释（exit 3=部分成功非致命，下轮自动补）；同步在 docs 写 exit 码语义。修改用户自己的 systemd unit 属工单授权范围（T9.3）。是否同意？

D8 (P1) T1 compose 端口默认值 8765→8767：会改变所有未设 TECHDB_QA_PORT 环境的部署默认。本机 .env 设了 8767（override），生产离线机无旧服务冲突。改默认值+文档说明 vs 保持默认+只加注释警示？我倾向改默认（新机一次到位，避免与旧 techdb-server 8765 冲突）。

D9 (P1) T10 engine .env 落点：改写到 pipeline/.env（引擎 load_env 向上 4 层内、非 vendored、已 gitignore 覆盖 .env）。vendored ENGINE_DIR/.env 若已存在则迁移并从 gitignore 移除该行（恢复 vendored 零写入声明）。是否同意？

D10 (P1) T12 生产实测：本机已有真实环境（canonical-qa 8767 + api + db），直接下载 feed 仓最新 daily zip → 调 /api/uploads(section=breadth, source=github)（走同一后端入口）→ 验证计数/队列清零/三索引计数增长/QA 召回。用 curl+JWT（管理员账号在 .env，测试脚本运行时读环境不回显）。是否可行？验收证据存 docs/qa-acceptance/。

D11 (P1) T11 同步到广度逐文件列：勘察 config 数组 upCfg 已逐文件（含 rowCfg）→ 改动小。做还是保持整批复选框？工单说"若改动小就改"。倾向做。

D12 (P0) T4 空 chunks 语义：upsert 记录正文/标题/摘要全空 → 标记 failed（last_error="empty payload"）。但合法空文本记录（占位/仅元数据）是否存在？导入链 title 必填 → 空文本不该出现。直接 failed 是否安全（不会误伤删除语义——delete 分支独立）。是否同意？

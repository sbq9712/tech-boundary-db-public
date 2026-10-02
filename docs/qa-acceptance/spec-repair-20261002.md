# 修复工单实施 Spec（2026-10-02）——T1~T12

依据：docs/qa-acceptance/repair-prompt-20261002.md（需求原文，含验收标准）+
docs/qa-acceptance/three-repo-audit-20261002.md（审计）。
Codex 决策轮：/tmp/repair/codex-rescue-1.out（D1-D12 全部收敛，D1/D2/D4/D6 带实现级修正，
已并入下文；原文存档于本文件附录）。

## 关键实测事实（勘察结论）

- G9 根因（实测复现）：发布视图存在同 (t,d,u) 重复行时，sync_qa_index.py 的 changed 取
  "首个差异行"而 kh_to_rec/基线取"最后一条"，keep_content_sha 与批次 csha 永不相等 →
  确认永不通过 → 每轮 exit 3。卡死键 8c218bc2…（大连化物所氢负离子电池，excel-import
  富化版 rec0 digest 1dab6f79 ≠ 基线 aca48fc7 = 贫瘠版 rec1）。
- canonical done 契约：answer_status/stop_reason/knowledge_boundary/claim_check(compact)/
  safety_hits/evidence/retrieval_trace；citations 无 grounding_status；supports_claim_ids
  由 answer_chain 回填（活字段）；claims 明细/reference_cards/evidence_summary 不在载荷。
- unsupported_major_claims = claim id 列表（非计数）——UI 按计数展示 + id 附加。
- incremental_index.load() 损坏路径 loaded=True 但内容清空 → health 恒 ready（G1 洞）。
- IndexTask 有 updated_at；api lifespan 起 breadth 队列 worker（默认开）。
- 引擎 load_env 从引擎模块目录向上 4 层找 .env → pipeline/.env 命中且非 vendored。
- 前端均为经典 <script>（无 module）；breadth/qa.js 已有 _qaSafeUrl/_qaSafeHref 与
  Node 测试钩子（tests/js/test_qa_sse_parser.mjs）。
- compose：canonical-qa 宿主默认端口 8765（与旧 techdb-server 冲突）；healthcheck 未断言
  incremental_index_ready。
- 文档：服务器迁移说明.md（6 章）/DEPLOY.md/服务器迁移交付清单.md 均无离线日常更新章；
  README.md:16 幽灵脚本；services/canonical-qa/README.md 三处旧路径。

## 设计决策（D1-D12，Codex 收敛版）

1. **G9 修复（T9）**：差异评估统一为"发布视图规范化 winner"——按合并顺序（分片文件名排序、
   行序）同键取最后一条，winner map 唯一化后派生 fresh/changed/keep/mutate/基线，杜绝
   rec0/rec1 分裂。基线在 winner 去重记录集上构造。
2. **G9 安全网**：deferred 键累计 attempts（持久 state）；>6 次 → dead_letter.json
   （key/op/attempts/first_seen/last_seen/reason/winner_digest），后续轮次不再重试（恢复
   exit 0），日志醒目告警；winner_digest 变化或 --rearm-dead-letter 自动恢复；不推进基线
   （不谎报已同步）。
3. **T9.3**：breadth-pipeline.service 加 SuccessExitStatus=3（exit 3=部分成功、非致命、
   下轮自动补）；文档写明 0/3/其他语义。
4. **T3 损坏检测**：incremental_index 损坏时置 corrupt 标志（文件存在但损坏 → health
   incremental_index_ready=false → compose healthcheck unhealthy；文件不存在 → healthy）；
   持久 reset epoch（数据卷内 marker 文件，重启不丢）。
5. **T3 重放**：api worker 启动+每小时 GET /api/health，发现 reset epoch 变新 → 一次性把
   全部 status=done 且 op=upsert 任务重置 pending（幂等重放；delete 不重放——墓碑独立
   持久）。已确认 epoch 持久化（DB 单行表），避免 api 重启漏报。
6. **T4**：upsert 空 chunks → 任务 failed（last_error="empty payload: no indexable text"），
   走现有 retry/failed 机制；delete 分支与"记录已不存在视为 done"语义不变。
7. **T5 门户**：done 处理保留 answer_status/knowledge_boundary/claim_check/safety_hits 进
   extra，摘要级渲染（四态徽章/边界条/主张计数行/安全命中/verification 摘要），全字段
   缺失优雅降级；不伪造逐 claim 粒度。
8. **T6 广度**：删死分支（claims 明细卡、reference_cards spans/source_role/快照漂移、
   grounding 徽章）；evidence_summary 由 claim_check 派生（requirements_total=claims_total、
   requirements_supported=claims_supported）；新增 knowledge_boundary 条、safety_hits 提示、
   unsupported_major_claims 计数（id 附加）；supports_claim_ids 活字段保留。
9. **T7 共享安全 URL**：assets/lib/safe_url.js（IIFE 挂 window.TechDBSafeUrl + CommonJS
   导出供 Node 测试），index.html/breadth/index.html 先于 app.js/qa.js 加载；qa.js 保留
   _qaSafeUrl/_qaSafeHref 别名（委托共享实现，测试钩子不变）；app.js inlineMd 链接过白名单
   （剥控制字符 + http/https/mailto + %22 编码引号），新增 XSS 单测。
10. **T8 token**：canonical-qa 写端点（upsert/delete/record-mutate）对"未配置或占位符"
    返回 503 明确错误；api 启动检测占位符打 WARNING；.env.example 写生成方法与两侧同值
    说明；部署编排：本机先生成真实 token 写入本地 .env（不入库）→ 同步写
    runtime/qa-index-sync/token（0600，管线用）→ 重建/重启 canonical-qa+api → 实跑验证写链路。
11. **T10**：engine_triage .env 改写到 pipeline/.env（合并既有、原子写 0600）；若 vendored
    ENGINE_DIR/.env 已存在则迁移；.gitignore 校验后移除 vendored 精确规则；容器 pytest
    import 修复（多级回退查找 scripts/）。
12. **T11**：上传弹窗"同步上传到广度"改逐文件列（默认否），后端 sync_breadth 逐文件语义
    已有；保留整批勾选作为批量快捷开关（作用于全部文件，等价原有行为）。
13. **T12**：本机真实演练（下载 feed 仓最新 daily zip → /api/uploads section=breadth
    source=github → 计数/队列清零/三索引增长/QA 召回），证据入 docs/qa-acceptance/。
14. **T1**：退役文档 + techdb_retire.sh（dry-run 默认；--execute 需
    TECHDB_RETIRE_CONFIRM=I-AM-SURE）；README 幽灵引用改真实脚本；canonical-qa README 三处
    改本仓库路径；compose 宿主默认端口 8765→8767（容器内 8765 不变）；本机 .env 去重
    TECHDB_QA_PORT 行（仅本地，不入库）。
15. **T2**：服务器迁移说明.md 新增"日常数据更新（离线环境）"章（下载/上传/确认/故障处理），
    DEPLOY.md 与交付清单交叉引用。

## 实现顺序与提交切分（每票一 commit）

1. T9（sync winner 修复+dead-letter+SuccessExitStatus+exit 码文档；live 验证 exit 0）
2. T3（corrupt 检测+epoch+api 重放+healthcheck+测试）
3. T4（空 chunks failed+测试）
4. T8（token 代码+.env.example+文档+本机部署编排+live 验证）
5. T10（engine .env 迁移+pytest import 修复）
6. T7（safe_url.js+app.js inlineMd+HTML 加载+测试）
7. T5（门户核验渲染+测试）
8. T6（广度 qa.js 对齐+测试）
9. T11（逐文件同步列+测试）
10. T1（退役文档+脚本+README/compose 修正）
11. T2（离线日常更新文档）
12. T12（真实演练+证据报告）

## 测试与验收

- 每 ticket：对应单测/契约测试 + 工单验收标准逐条核对（DoD 见 repair-prompt）。
- 全量：backend pytest（本机 venv 与容器内）、node tests/js、docker compose config。
- Codex review：三批（后端/前端/文档+演练），REQUEST_CHANGES 循环修复至 APPROVE。
- 收尾：交接包（任务矩阵/证据/遗留风险/自动裁决记录）+ push GitHub main。

## 附录：Codex 决策轮原文

见 docs/qa-acceptance/codex-repair-decisions-20261002.md；决策问题原文见 docs/qa-acceptance/grill-decisions-20261002.md（均与本 Spec 同 commit 落盘）。

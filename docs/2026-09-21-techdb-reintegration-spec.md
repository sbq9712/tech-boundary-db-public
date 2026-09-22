# Spec: tech-db（前者）完完全全重新接入 tech-boundary-db（后者）

状态: IN_PROGRESS · 起草: 2026-09-21 · 自动裁决记录见文末
原始任务: 用户 2026-09-20 晚下达（全文见 git history / 会话记录），要点：

1. tech-db 是 tech-boundary-db「广度追踪」功能的上游；其「知识库问答」
   对应门户「对话」功能。把 tech-db 全量重新接入 boundary，替换旧版本。
2. 领域分类 77 叶 → 125 叶（与 boundary 行业图景一致）；「不相关/未分类」
   保留功能性角色。换分类后重跑 pipeline（至少分类）。
3. tech-db 每 4h 自动检查 3 个子仓库并抓取跑批——接入后该职责由 boundary
   侧整体接管。
4. 先在老仓库完成分类改版+重跑，再接入新仓库。

## 关键决策（自动裁决，无用户待决项）

| # | 决策 | 理由 / 备选 |
|---|------|------------|
| D1 | taxonomy 三文件 = 125 叶（不含 不相关/未分类）；validator 的 allowed = taxonomy ∪ SPECIAL | 干净的 VALID_CATEGORY_LEAVES（评分/摘要不再扫不相关记录）；功能角色由 data_contract.SPECIAL_CATEGORIES 保留；备选（127 含特殊标签）会浪费每晚 token 且污染提示词白名单 |
| D2 | 重分类范围 = 所有 c∉新125叶 记录（49,764）| 用户点名"至少分类重跑"；旧 66 叶全部失效 |
| D3 | 评分=仅重分类到叶子的记录；摘要=新叶子缺 as；kp=新叶子缺 kp；聚类=变更族整体解除 | 时间/token 平衡；validator 安全 |
| D4 | GLM glm-5.3-flash（用户指定）；llm_client.call_glm_batch batch10/workers5 | 实测 2.6s/批 |
| D5 | 断点 checkpoint + run fingerprint + 发布闸门 + validator 回滚 | Codex review 修复 #1#2 |
| D6 | portal hooks（alert/focus/calendar 深链）重新移植进新 app.js；QA tab/qa.js 剥离（门户对话拥有 QA UI）| 用户任务 1；上游 UPSTREAM.md 惯例 |
| D7 | breadth 前端 = tech-db HEAD 三件套（index/app/styles）− QA + portal hooks；index.html 版本参数 bump | 用户任务 1 |
| D8 | canonical-qa 资产 = tech-db 新索引（vector/bm25/graph/lite）+ manifest 重算（新 upstream_commit/记录数/索引数/SHA）| check_assets fail-closed 契约 |
| D9 | auto-update 接管 = boundary 侧 systemd timer 跑 tech-db pipeline（ALLOW_LOCAL_STATE_ADVANCE）+ 数据落 boundary breadth + canonical-qa 资产刷新 + 双仓库 push | 完全接管；备选（跨仓库 push tech-db）交叉权限风险大，弃 |
| D10 | record_id_map 重建（dataset sha 变化），registry 保留（stable ID 复用）| index_build_view 契约 |
| D11 | Hermes Agent：仅清除 git 署名与闲置 systemd unit；不改写历史（需 force push，高风险，用户未明确授权）；headroom-hermes-proxy 在用不动 | 用户"删掉但不破坏功能" |

## Tickets

| # | 内容 | 状态 | DoD |
|---|------|------|-----|
| T1 | taxonomy 三文件 125 叶 | DONE ed2d422 | load_taxonomy==load_category_order==125 |
| T2 | reclassify_taxonomy_v2.py | DONE 4f0a807 | 冒烟 40 条全阶段 OK；Codex review 5 条处理 |
| T3 | 全量重分类跑完 + snapshot | IN_PROGRESS | validator 绿；分类后白名单外=0 或未分类待自愈 |
| T4 | conferences/graph/record_id_map/bm25/vector 重建 | PENDING | 索引文件 mtime 新；服务器 health ok |
| T5 | tech-db 数据 commit + push main | PENDING | push 成功（main 今日可推）|
| T6 | breadth 前端替换（-QA +portal hooks）| READY(已预制) | node --check；portal 深链 3 参数生效 |
| T7 | hydrate pins + Dockerfile gate 33 分片 | PENDING | hydrate --check 绿 |
| T8 | alert/category-counts 重建 | PENDING | 两 derived json 生成 |
| T9 | canonical-qa 资产+manifest 刷新 | PENDING | check_assets.py 绿 |
| T10 | 4h auto-update 接管（timer+sync 脚本）| PENDING | 干跑一次成功；timer 使能 |
| T11 | contract/portal 测试回归 | PENDING | docker compose exec api pytest 全绿（已知3个历史失败除外）|
| T12 | 双仓库 push + 交接包 | PENDING | remote 刷新后推送；交接包含 SHA/决策/偏差/风险 |

## 偏差记录
- 管线 timers（techdb-pipeline/data-sync/vector/graph）在重分类期间暂停，
  完成并索引重建后恢复（防并发写坏 lite/shards）。
- D5 修复后弃用旧进程（kill 566781），checkpoint 续跑无损。

## PR #1 评审项闭环（2026-09-22）
阻塞项 ①②③ 于 0cf5c94 修复并合入。非阻塞项 ④-⑧（原定"下轮迭代"）本轮全部落地：
- ④ 用户管理副标题删除 —— 随 2026-09 UI 改版完成。
- ⑤ 侧边栏"历史对话"区块（logo 列表下方、收起/展开切换按钮 + 会话列表整体滚动）—— v5/v6 完成，
  Playwright 断言折叠为 computed display:none。
- ⑥ TZ=Asia/Shanghai —— docker-compose 四服务（db/canonical-qa/api/readonly-agent）统一注入。
- ⑦ README 状态章节 —— 更新至 2026-09-22（tech-db 125 叶子基线、4h 接管、UI 改版）。
- ⑧ 登录失败提示 —— 核对为已满足：后端区分「用户名或密码错误/账号已禁用/限流」，
  前端透传 detail，无通用化文案，不需改动。
另：评审建议的 TECHDB_INGEST_MAX_CONCURRENCY 全局并发闸门一并落地（默认 2，0=不限）。

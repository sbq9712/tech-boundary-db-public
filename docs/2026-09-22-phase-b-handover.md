# Phase B 收编 + PR#1 评审 + UI v6 —— 交付纪要（2026-09-22）

## 一、仓库与分支
| 仓库 | 角色 | 分支/PR | 关键 SHA |
|---|---|---|---|
| sbq9712/tech-db | 广度追踪+管线数据源（上游） | main | `c00d7b9`（125 叶子全量重分类基线） |
| sbq9712/tech-boundary-db | 门户项目（fork，开发侧） | main → PR #1 (EDMUNDSdaONE/tech-boundary-db) | `7cdb044` |
| EDMUNDSdaONE/tech-boundary-db | 主仓 | PR #1 OPEN，head=7cdb044 | — |

## 二、数据基线（B 阶段）
- 分类法：125 叶子目录，65,605 条记录，33 shards，`data_version=c3a54b75d9d3`，基线 commit `c00d7b9`。
- hydration 钉扎：`scripts/hydrate_breadth_runtime.py`（UPSTREAM_COMMIT/DATA_VERSION/RECORDS/SHARDS/FILES 全校验）。
- 4h 自动更新接管：`scripts/auto_update_takeover.sh`（动态改写全部 pins）+ systemd user `techdb-auto-update.{service,timer}`；
  timer 待向量索引完成后由 finish-watcher 自动启用。
- 向量索引重建（44,799 chunks，GLM 5.3-flash 分类底座）：运行中，完成链
  `vector_completion_chain.sh`（重启 techdb-server → refresh_qa_assets）+
  `phaseb_finish.sh`（canonical-qa 镜像重建 → manifest 提交 → timer 启用）全自动，日志 `/tmp/vector_chain.log`。

## 三、PR #1 评审闭环
- 阻塞 ①②③：0cf5c94（已合入）。
- 非阻塞 ④-⑧：全部落地（详见 `docs/2026-09-21-techdb-reintegration-spec.md` 闭环章节）。
  ④用户管理副标题（UI 改版中完成）；⑤历史对话折叠区（v5/v6）；⑥TZ=Asia/Shanghai（08db98d）；
  ⑦README 状态章节（08db98d）；⑧登录失败提示（核对为已满足，无需改动）。
- 评审建议的 TECHDB_INGEST_MAX_CONCURRENCY 信号量：08db98d 落地，bd89cbf 按 Codex 意见透传 compose。

## 四、UI v6（用户第 5 轮反馈）
- 侧边栏 logo 几何以收起态为基准：brand 16 / nav 8 / account 12 → 全部 img x=17，两态一致（22px）；
  收起/展开图标全态 22px；导航按钮纵向位置两态不变。
- 「历史对话」折叠失效根因修复：`.sidebar-conversation-list{display:flex}` 覆盖 `[hidden]`（64afc2f）。
- 资料库列表不再显示原文件名；上传弹窗表格化（去密级/来源类型、初始仅拖拽区、一行一文件、
  原生 date、逐行独立上传）。Codex P1 修复：行状态以 upPending 为唯一事实源（bd89cbf）。
- 验证：契约测试 9/9；Playwright 25/25（真实上传+删除清理闭环）；后端 160 pass（3 项既有失败与基线一致）。

## 五、Codex 评审（必须实际调用）
- 历史：本会话早期 3 次尝试全部网络失败（EXIT=124）——根因于本日定位：
  `codex-zai-proxy.service`（127.0.0.1:4567，Responses→Chat 翻译代理）依赖的
  `~/.local/bin/node` 缺失。已用官方 node v22.14.0 恢复（`~/.local/node`），
  服务恢复 active，proxy 探活 200。
- v6 评审：EXIT=0，无 P0；3×P1 + 1×P2 全部处理（bd89cbf）。
  原稿存档：`docs/codex-reviews/2026-09-22-v6-ui-review.md`。

## 六、Hermes 清理（已授权，2026-09-22 执行）
- 删除：`hermes-gateway.service`（unit 删除）、`~/.hermes`（20GB）、`~/.local/bin/hermes`、`.bashrc` 音效 hook。
- 保留：`headroom-hermes-proxy.service`（仅名字含 hermes，读 `~/.headroom`，独立在用）、
  `readonly-agent` HTTP 链路（HERMES_AGENT_MODE=http，在用功能）。
- 事故与修复：`codex-zai-proxy` 的 node 依赖随清理受损，同日修复（见上）。仓库内 hermes 代码引用未动（避免破坏 /assistant/query）。

## 七、自动决策记录（本轮新增）
- D7-D13（UI v6 细节）：`docs/2026-09-21-sidebar-redesign-spec.md`。
- D14 登录错误提示判定为已满足（不改动）：后端已区分错误类型，前端透传 detail。
- D15 Hermes 清理边界：代码级 hermes 引用（bridge/readonly-agent）不动，仅删基础设施与数据。

## 八、残留风险 / 待观察
1. canonical-qa 在系统高载（向量构建 load≈19-20）下增量索引 upsert/delete 较慢：
   上传 POST 同步等待索引写入，大文件在高载下可能超时（TECHDB_QA_INDEX_TIMEOUT_SECONDS=300 兜底）。
   向量构建完成后即消失。
2. 删除资料时若 QA 索引删除超时（nginx 60s 先 504），记录不会被删——幂等，重试即成功；
   前端提示「删除失败」可重试，属可接受体验。
3. nginx 对 api 的代理超时（60s）短于 QA_INDEX_TIMEOUT（300s）：极端高载下前端会先看到 504。
   建议下轮迭代对齐两处超时。
4. tech-db 下一个 bot 提交（00:00 CST 后）将验证 4h 接管链路；pins 动态改写已就位。
5. PR #1 mergeable 状态由 GitHub 计算中（推送后短暂 UNKNOWN 属正常）。

## 九、验证命令备忘
```
docker compose exec api pytest -q                      # 后端全量
docker compose exec api pytest tests/test_portal_ui_contract.py -q
# Playwright 25 项：/tmp/ui_v6_test.py（几何/折叠/上传两阶段/真实上传删除/列表去文件名）
curl -s http://localhost:8080/ | grep -o ui4[0-9]      # 前端版本（当前 ui48）
systemctl --user is-active codex-zai-proxy headroom-hermes-proxy
```

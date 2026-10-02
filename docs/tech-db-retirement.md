# tech-db 退役核对清单（T1，2026-10-02）

> 背景：广度追踪数据链已由本仓库（tech-boundary-db）自持——上游
> [sbq9712/tech-boundary-data-feed](https://github.com/sbq9712/tech-boundary-data-feed)
> 每日发布包交付 + 本仓库自有 4h 管线（分类/评分/发布）。旧仓
> [sbq9712/tech-db](https://github.com/sbq9712/tech-db)（本机 `~/tech-db` 与
> `~/tech-db-fresh` 两份检出 + systemd user 单元）进入退役流程。
>
> **本仓库不执行任何退役动作**：本文档与 `scripts/techdb_retire.sh` 只提供
> 核对清单与命令演练（dry-run）。真正的 disable/删除由维护者按清单手工执行
> （`~/tech-db-fresh` 与其 systemd 单元明确不在本仓库脚本的操作范围内）。

## 1. 删库前必须确认（全部满足才继续）

| # | 确认项 | 命令 | 通过标准 |
|---|--------|------|----------|
| 1 | 新链管线连续 ≥3 个周期成功 | `systemctl --user list-timers breadth-pipeline.timer` 然后 `journalctl --user -u breadth-pipeline -S "-24 hours" \| grep -c "exit-code=0"`（或查看 SuccessExitStatus=3 的部分成功日志说明） | 定时器 active；近 24h 内 ≥3 次运行且无 failure；`systemctl --user show breadth-pipeline -p SuccessExitStatus` 含 3（部分成功是设计态） |
| 2 | 最近一次 feed 包发布成功且可下载 | 浏览器/`curl -sI` 检查 `https://sbq9712.github.io/tech-boundary-data-feed/`（或 GitHub Releases/Actions 最新产物）| 最新 daily zip 可下载且生成时间在预期周期内 |
| 3 | QA 基础索引已本地重建 | `python3 scripts/rebuild_qa_base_index.py --help`（已具备）+ `curl -s http://127.0.0.1:8767/api/health \| python3 -c "import json,sys;d=json.load(sys.stdin);print(d['total_records'],d['incremental_index_ready'])"` | total_records 与发布视图一致；incremental_index_ready=true |
| 4 | 门户全链路无 tech-db 依赖 | `grep -rn "tech-db" --include="*.py" --include="*.sh" --include="*.yml" backend/ pipeline/ scripts/ docker-compose.yml \| grep -v tech-boundary | grep -v retirement | grep -v 承接` | 无生产路径引用（文档/历史注释除外） |

## 2. 停用顺序（人工执行；脚本只演练不执行）

```bash
# ① 停定时器与隧道（顺序不可反：先隧道后服务会造成 502 尾流）
systemctl --user disable --now techdb-tunnel \
  techdb-server \
  techdb-data-sync.timer \
  techdb-pipeline.timer \
  techdb-graph.timer \
  techdb-vector.timer
# ② 确认旧站已 404（Pages 需在 GitHub 网页上手动关闭，无法 CLI）
curl -sI https://sbq9712.github.io/tech-db/ | head -1   # 预期 404
# ③ 观察一个新链完整周期后再删除本机目录与远端仓库
```

## 3. 删库后验证

tech-boundary-db 全链路（pipeline / feed 发布 / QA 检索 / 上传导入）运行一个
完整周期，`docker compose logs api canonical-qa` 与 pipeline journal 中
**不得出现任何 `/home/rhett/tech-db*` 路径或 `techdb-*` 单元名**的报错
（本仓库已切换 8767 端口，canonical-qa 不再依赖 8765 的旧服务）。

## 4. 数据漂移说明（删库前唯一需要数据侧确认的项）

- **现象**：tech-db-fresh lite 69,471 条 vs tech-boundary-db 69,368 条，
  差 103 条。
- **原因**：旧链 2h 步调 vs 新链 4h 步调——旧链最后一次运行抓到了新链两次
  周期之间发布的增量，属发布节奏差，非丢数据。
- **差异条目查询方法**（按 content_hash 对比两库 breadth 表）：

```sql
-- 旧库（tech-db-fresh，删除前执行）
SELECT content_hash FROM breadth
EXCEPT
SELECT content_hash FROM breadth;   -- ← 在新库执行另一半，两向各查一次
-- 等价 shell（两边各导出 hash 后 diff）：
-- 旧库: psql -c "COPY (SELECT content_hash FROM breadth ORDER BY 1) TO STDOUT" > /tmp/old.hash
-- 新库: psql -c "COPY (SELECT content_hash FROM breadth ORDER BY 1) TO STDOUT" > /tmp/new.hash
-- diff /tmp/old.hash /tmp/new.hash | grep '^<' | wc -l   # 旧有新无
```

- **是否需要补齐的判断标准**：
  - 若差异条目均为 **>7 天前** 的记录 → **以新库为准，无需补齐**（下一轮
    上游 feed 包会按发布视图重新覆盖口径）。
  - 若差异条目含 **近 7 天内** 的记录 → 新链可能漏采：用
    「资料库 → 广度追踪 → GitHub 广度情报」手动导入最近 feed 包补齐，
    并排查 4h 定时器 journal。
- **默认结论：以新库为准，无需补齐**（103 条差异全部为步调差产生的旧周期
  边缘记录；2026-10-02 审计未见新库缺近 7 天数据）。

## 5. 配套改动（本仓库内，已完成）

- `docker-compose.yml`：canonical-qa 宿主默认端口 8765 → **8767**（8765 是
  旧 techdb-server 遗留占用；容器内仍 8765，`.env` 的 `TECHDB_QA_PORT`
  可覆盖）。本机 override 未加端口映射——如需临时改回，在
  `docker-compose.override.yml` 的 canonical-qa 下加
  `ports: ["127.0.0.1:8767:8765"]`。
- `README.md` 数据源一节改为自持链路描述（原指向 tech-db 管线为幽灵引用）。
- `services/canonical-qa/README.md` 三处 `cd /home/rhett/tech-db-fresh` 改为
  本仓库路径 `~/tech-boundary-db/services/canonical-qa`。

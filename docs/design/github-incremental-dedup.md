# GitHub 广度情报增量包：导入去重契约（已实现）

状态：**已接入**（2026-09-28，迁移 0026）。包格式为 tech-boundary-data-feed 的
`daily/YYYY-MM-DD.zip`（feed-pkg/v1）；上传入口为资料库-广度追踪-GitHub广度情报。
实现：`backend/app/services/github_import.py`（导入/校验/去重）+
`backend/app/routers/uploads.py`（上传通道）+ `breadth_import_sessions` 会话表；
测试：`backend/tests/test_github_incremental_import.py`。

## 1. 交付物与记录粒度

- 一个增量包 = 一个上传文件（zip/tar），落在 `uploaded_files`，`primary_section='breadth'`、`breadth_source='github'`。
- 解包后的每条情报 = 一条广度总表记录。**不做** 1 文件 = 1 记录（与其他广度情报的人工上传语义不同）。

## 2. 去重键（dedup key）

与广度总表既有幂等语义保持一致，读侧去重键为：

```
t|d|u   →  (title, document_date, url)
```

- 三元组完全一致视为同一条记录；`title` 按去除首尾空白后比较，`u` 为空时用内容 SHA-256 前 16 位占位（`sha256:<prefix>`），保证空 URL 不产生跨源碰撞。
- 增量包内重复（同包多条同键）：保留日期最新一条，其余丢弃并计数。
- 与库内既有记录撞键：跳过导入并计数，不更新已有记录（上游基线只读原则，见 docs/UPSTREAM.md）。

## 3. 幂等重放

- 每个增量包在导入前计算整体 `checksum_sha256`（沿用 `uploaded_files.checksum_sha256`）。
- 同一包重复提交：直接返回上次导入结果（成功/部分成功清单 + 各类计数），不再解包。
- 包内解析中断：已入表条目保留，导入会话记录断点（包内偏移），重试仅处理余量。

## 4. 结果语义

导入会话返回：

```json
{
  "imported": 120, "skipped_duplicate": 34,
  "skipped_upstream_conflict": 2, "failed": 0,
  "package_deduplicated": true
}
```

- `页面完成 ≠ 导入完成`：前端 GitHub增量包 页面在协议接入前只展示"待接入"；
  接入后本契约的计数必须逐项透出，不允许把 skipped 归并进 imported。

## 5. 明确不做

- 不回写、不重建既有知识库基线索引（65,605 条上游记录只读）。
- 不在导入时改写任何已有记录的 `level`（人工等级仅由库内人工操作变更）。
- 不为对齐增量包而修改广度总表分片结构（`breadth/data/processed/*`）。

## 附：qa-index-sync 与管线退出码语义（2026-10-02 G9/T9）

`pipeline/auto_pipeline.py`（systemd `breadth-pipeline.service`，4h 一轮）：

| 退出码 | 含义 | systemd 显示 |
|---|---|---|
| 0 | 全部步骤成功 | Finished |
| 3 | 部分成功（典型：QA 索引同步有 update/delete 待服务端确认、失败任务重试未收口；非致命，下一轮自动补推） | Finished（unit 已声明 `SuccessExitStatus=3`） |
| 其他 | 真实失败（状态不 commit，下一轮自动重试） | Failed |

`scripts/sync_qa_index.py` 的确认协议补充（G9 修复）：

- 同 `(t,d,u)` 重复行按「发布视图规范化 winner」（分片文件名排序 + 行序，
  同键取最后一条）收敛——fresh/changed/keep/mutate/基线全部使用同一 winner，
  不再出现"changed 取首个差异行、基线取最后一条"的分裂（曾致 8c218bc2…
  键永久 pending、管线每轮 exit 3）。
- 遗留 pending op 若 winner 已与基线一致（无新内容可送）会被清理，不再重试。
- 连续 `DEAD_LETTER_MAX_ATTEMPTS`（默认 6）轮无法确认的键转
  `runtime/qa-index-sync/dead_letter.json`（记录 op/attempts/first_seen/
  last_seen/reason/winner_digest）：停止重试（管线恢复 exit 0）但**基线不推进**
  （绝不把未确认的同步谎报为已完成）；键内容变化自动恢复重试，或
  `--rearm-dead-letter` 人工恢复。

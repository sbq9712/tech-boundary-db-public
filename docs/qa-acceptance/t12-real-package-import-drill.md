# T12 生产实测：真实 GitHub daily 包离线导入全链路演练（2026-10-02）

> 任务：在本地用真实产物演练完整离线流程——下载 sbq9712/tech-boundary-data-feed
> 最新 daily zip → 走「资料库-广度追踪-GitHub广度情报」同一后端入口上传 →
> 确认导入计数、队列清零、三索引计数增长、QA 召回新记录。
> 结果：**四步证据齐全**；演练暴露并根修 **3 个真实缺陷**（其中 1 个为
> 「增量导入记录永远召不回」的严重检索缺陷），全部修复后复测通过。

## 0. 包获取与前置验证

| 包 | 大小 | 说明 |
|---|---|---|
| daily/2026-10-02.zip（最新） | 69,159,550 B | sha256 与 LATEST.json 一致；validator 11 项全过；演练 v1/v2 记录来源 |
| daily/2026-09-30.zip | 641,126 B | sha256 一致；validator 全过；原包整体上传演练 |
| daily/2026-10-01.zip | 745,425 B | **manifest_digest 校验失败（发布端问题，已记录未修）** |
| daily/2026-09-29.zip | 57,489,299 B | zip 损坏（CRC），跳过 |

下载方式：`curl -C -` 断点续传循环至 sha256 与 LATEST.json `package_sha256`
一致（raw.githubusercontent 大文件单次下载必截断）。

## 1. 第一步：导入计数（两个视角）

### 1a. 真实 09-30 包整体上传（API 直调，同一后端入口）

```
POST /api/uploads  files=2026-09-30.zip  primary_section=breadth  breadth_source=github
→ 201 {"package_date":"2026-09-30","record_count":383,"imported":0,
       "skipped_upstream_conflict":383,"failed":0}
note: "导入 0 条 · 撞库跳过 383"
```

383 条全部 `skipped_upstream_conflict` 是**设计行为的正确触发**：
`github_import._apply_changes` 对 ADD 先查上游基线
（`_upstream_key_digests` = 本机 breadth 分片全量 t|d|u 键集），键在上游
即判「上游拥有」跳过。本机（开发机）跑着本地管线、上游数据比 09-30 包
更新，故全部撞库；**真正离线服务器上没有本地上游数据，同一包会全量导入**
（离线语义正是如此——v2 演练包用「键不在上游」的记录完整模拟了该环境）。

DB 证据（演练后仍保留）：`breadth_import_sessions` 一行
`2026-09-30 | record_count=383 | imported=0 | skipped_upstream_conflict=383 | replayed=f`。

### 1b. v2 演练包：5 条「基线索引里不存在」的真实记录（离线新记录等价物）

从**最新 10-02 包** 69,359 条中选出 845 条「URL 不在基线索引
（all-records-lite.json 68,516 URLs）」的新记录里的 5 条（Crawzilla 螯虾 /
福特级航母 / 200GW 电网 / MV6 麦克风 / 虚拟电厂选型），标题加 `【T12演练】`
前缀（生成新 t|d|u 键 → 不撞上游 → 走完整 ADD 路径），manifest/changes/
digests 全部重算，validator 11 项全过：

```
→ 201 {"imported":5,"details":{"added":5,"failed":0,...}}
```

v1 演练包（15 条：b=91,771/61,725/60,479 长正文 + cp 标量 int + 普通记录）
同路径 `imported=15, added=15, failed=0`。

## 2. 第二步：队列清零

```
v1: breadth_index_tasks  processing 15 → 轮询 ~150s → 0（done 28→43）
v2: +5 任务 → 轮询 ~32s  → 0（done 43→48）
清理: 20 个 delete 任务 → 秒级清零（done 48 = 23 upsert + 25 delete）
failed 恒为 3（2026-09-28 崩溃恢复验收故意构造的 malformed 任务，与本演练无关）
```

## 3. 第三步：三索引计数增长（canonical-qa /api/health）

| 指标 | 演练前 | v1 后 | v2 后 | 清理后 |
|---|---|---|---|---|
| incremental_documents | 8 | 23 (+15) | 28 (+5) | **8（精确还原）** |
| incremental_records | 968 | 1029 (+61) | 1047 (+18) | **968（精确还原）** |
| total_indexed_records | 69491 | 69552 (+61) | → | 69491 |
| incremental_corrupt | false | false | false | false |

vector/bm25 基线计数（68,523）不变是架构设计：增量先入 incremental 索引，
基线索引按发布周期重建，检索时两路 RRF 融合。

## 4. 第四步：QA 召回新记录（暴露严重缺陷 → 根修 → 复测）

### 4a. 缺陷现象（api:1009 + canonical-qa:1003）

`/api/search?q=Crawzilla 北美最大螯虾` 前 10 全是弱相关基线记录，
增量导入的 Crawzilla 记录无影无踪。直测 `hybrid_search` 该记录 **rank1
（score 0.0321）**——检回了、但 orchestrated_search 输出里消失。

### 4b. 根因

`server._hydrate_texts` upload 分支只读 `filename/title/chunk_text/text`，
而 `incremental_index.upsert` 写入的 meta 是统一记录形字段 `t/d/c/as/b/tg`
（两个键集根本不相交）→ 记录型 chunk（feed 导入、管线同步）hydrate 成
**空标题/空正文/空日期** → rerank 词覆盖恒 0、TEMPORAL 新鲜度 0，
`final = prior×0.6`，永远排在任何有一点词覆盖的基线记录之后。
**离线服务器上导入的全部新记录都会如此——QA 永远召不回增量新记录。**
（手动上传 chunk 的 body_snippet 同理恒空，属同根遗留。）

### 4c. 修复（commit「fix(qa): 增量导入记录 hydrate 空文本根修」）

upload 分支补 `t/d/c/as/b/tg` 兜底（与基线记录同公式），
filename/title/chunk_text 优先级不变（手动上传行为不变）。
回归测试 `test_hydrate_upload_texts.py` 9 项（含「hydrate 后 rerank 词覆盖
不再恒 0」语义断言）。镜像 `techdb-canonical-qa:1004` 已部署。

### 4d. 复测（canonical-qa:1004）

```
/api/search?q=Crawzilla 北美最大螯虾      → rank1 = 【T12演练】'Crawzilla'… ✓
/api/search?q=福特级航母第二艘 2027年交付 → rank1 = 【T12演练】10万吨级福特级… ✓
/api/search?q=虚拟电厂平台服务商 选型指南 → top5 内含 T12 记录 ✓
POST /api/chat/stream {"query":"北美已知最大的螯虾叫什么？…"}
→ 回答全文引用 [1]（SciTechDaily，即增量导入记录），answer_status=
  PARTIALLY_SUPPORTED、citations/claim_check/knowledge_boundary 契约完整
```

清理后同 query 不再召回（删除全链路生效的旁证）。

## 5. 演练中根修的缺陷清单

| # | 缺陷 | 根修 | commit |
|---|---|---|---|
| 1 | cp 标量 int（根记录聚类 flag）被当非法形态，近期每日包全量拒收 | 导入端/校验器容忍 int cp（0/1/42） | d57dc10 |
| 2 | b>20k 整包 400 拒收（10-02 有 37 条，最长 91,771） | `_BODY_CAP`(20k 截断) 与 `_BODY_HARD_REJECT`(200k 拒收) 分离；生成端 normalize_record 截断 | d6aad46 |
| 3 | 增量导入记录 hydrate 空文本 → QA 永远召不回 | `_hydrate_texts` 记录形字段兜底 | （本文件同批） |

发布端遗留（记录未修，属 tech-boundary-data-feed 仓）：
- 10-01 包 manifest_digest 校验失败；
- 10-02 包 `predecessor: "chainX"` 疑似占位符未填（sequence=4）；
- 09-29 包 zip 损坏。

## 6. 清理与还原

- 两个演练上传（v1 15 条 / v2 5 条）经 `DELETE /api/uploads/{id}` 删除：
  `{ok:true, queued_record_deletes:15/5}` → 20 个索引删除任务清零，
  incremental 计数精确还原到演练前（8 docs / 968 records），
  `breadth_manual_records` 中 T12 演练行 = 0。
- 09-30 真实包上传与其 import session 保留为 DB 证据（0 导入 383 撞库）。

## 7. 环境与镜像

- api `techdb-api:1009`（b 上限分离）、canonical-qa `techdb-canonical-qa:1004`
  （hydrate 修复），均基于当日基线增量构建并 `docker compose up -d
  --force-recreate` 生效；.env 对应 TAG 已更新。
- 端口：api 8080 / canonical-qa 8767（容器 8765）。

## 8. 复现步骤（离线服务器同构）

```bash
# 1. 下载（断点续传至 sha256 匹配 LATEST.json）
curl -C - -o pkg.zip https://raw.githubusercontent.com/sbq9712/tech-boundary-data-feed/main/daily/2026-10-02.zip
python3 scripts/validate_feed_package.py pkg.zip
# 2. 上传（或页面 资料库→广度追踪→GitHub广度情报）
curl -F files=@pkg.zip -F primary_section=breadth -F breadth_source=github \
     -H "Authorization: Bearer $TOKEN" http://<host>:8080/api/uploads
# 3. 队列/索引/召回
psql> SELECT status,count(*) FROM breadth_index_tasks GROUP BY status;
curl http://<host>:8767/api/health          # incremental_documents/records 增长
curl "http://<host>:8767/api/search?q=<新记录标题>&top_k=5"
```

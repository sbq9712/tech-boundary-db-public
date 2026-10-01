# 情报类型全量对齐 triage_engine + 门户问答生产切换（2026-10-01 深夜）

## 用户诉求

1. 广度页（index.html#breadth）情报类型中「新闻/文献」下属类型未与
   triage_engine 同步 —— 需要全量对齐新展示分类（新闻 7 类 + 文献 4 分型）。
2. techdb 知识库问答未很好迁移到 tech-boundary-db 门户问答 —— 需要完成迁移。

## 一、类型同步：全量重分诊

### 根因

- a1f52a0（2026-10-01 14:45）修复了 engine_triage.py 的标签降维
  （旧适配层把引擎 7+4 展示链压回旧 5+2），但 **9/28 的全量重分诊
  checkpoint 未失效**：6.8 万条已处理记录携带旧标签，修复只对增量生效
  （当晚新入 238 条为新口径）。
- 旧→新映射有损（产业进展 ← 工程与产业化+资源市场与产业链；行业观察 ←
  人才与组织动态+观点与交流+默认），无法离线反解，必须重跑引擎
  （DISPLAY_CHAIN_MAP 键为引擎 typeId T01–T25，lite 不存）。

### 执行（LLM-on，与 auto_pipeline 默认一致）

```
TRIAGE_RETRIAGE_WORKERS=6 TRIAGE_LLM_BATCH=8 TRIAGE_LLM_SLEEP=2.0 \
  .venv/bin/python scripts/rerun_engine_retriage.py --reset-checkpoint --batch 400
```

- 20:35 启动、23:22 完成（约 2 小时 47 分），期间暂停 breadth-pipeline.timer
  防并发写（auto_pipeline 与重跑共用 lite/分片两写者，无共同锁）。
- 结果（对比 9/28 首跑）：
  - ok=69368 fail=0；不相关 27,438（39.6%）↔ 9/28 39.6%
  - scored 41,930 ↔ 41,063；featured 3,943 ↔ 3,851（增量 341 条所致）
  - 引擎判定稳定，无方向漂移。
- 数据契约：不相关记录 AI 字段清零（irrelevant-with-AI-fields=0）；
  人工字段（lv/wr/cm/fb）与摘要/参数/聚类原样保留。
- 回滚资产：runtime/retriage-20261001/（lite/checkpoint/env 备份）。

### 发布链路 bug（本次发现并修复）

publish_to_boundary 是「镜像安装」——只搬运 pipeline/data/processed 下
已生成的 lite-part 分片，不读 all-records-lite.json。重跑脚本只写 lite，
首轮发布把旧标签分片原样装回（线上 69,368 条仍旧口径）。修复：
rerun_engine_retriage.py 发布前先 build_snapshot(lite) 重建分片。
修复后线上分片 100% 新口径（auto-20261001-2331）。

### 最终分布（69,368 条）

| 载体 | 标签 | 条数 |
|---|---|---|
| 文献 | 研究型 | 45,363 |
| 新闻 | 观点与交流 | 12,337 |
| 新闻 | 工程与产业化 | 3,412 |
| 新闻 | 资源、市场与产业链 | 2,688 |
| 新闻 | 企业经营、合作与资本 | 1,749 |
| 文献 | 新闻/评论/观点 | 1,728 |
| 新闻 | 政策、法规与标准 | 759 |
| 新闻 | 知识资产 | 527 |
| 新闻 | 人才与组织动态 | 357 |
| 文献 | 分析类 | 314 |
| 文献 | 综述 | 134 |

旧 5+2 标签清零；页面弹框（app.js TRIAGE_TYPE_TAGS）固定渲染 7+4，
数据中未知新类自动追加（未来引擎加类无需改前端）。

## 二、门户问答生产切换（:0801 → :1002）

- .env：TECHDB_QA/API/WEB_IMAGE_TAG=1002，AGENT 维持 0801（对照基准），
  INCREMENTAL_VOLUME 不变（增量索引 975 条 + 7 文档随卷保留）。
- canonical-qa：24,091 → **68,523** 基础索引（+975 增量 = 69,498），
  content_fingerprint=2c858254a7b8d651a4eebf36a9cc60ea（含增量内容）。
- api：alembic 0031 应用；/api/assistant/stream 鉴权 401 正常，
  带 token 端到端实测（固态电解质提问）：检索 25 条、结构化回答带
  引用编号与证据分级（「企业宣传口径，尚未见独立验证」）。
- web：breadth/app.js 含 TRIAGE_TYPE_TAGS/LEGACY_TYPE_TAGS，
  lite-part-0 抽查 100% 新标签。
- sync_qa_index --reset-baseline：基线重置为当前发布视图 69,368，
  下轮 data_version 未变幂等退出。
- 回滚：.env tag 改回 0801 + docker compose up -d（wu7 流程），
  数据回滚用 runtime/retriage-20261001/all-records-lite.backup.json。

## 三、验证清单

- [x] 重分诊 fail=0、不相关率与首跑一致（39.6%）
- [x] lite 与线上分片标签一致（69,368 条 100% 新口径）
- [x] 不相关记录无 AI 字段残留
- [x] 页面（:8080）数据为新标签、auto-version 2333
- [x] QA 健康（68,523+975）、e2e 问答带引用
- [x] api 常规端点（auth/dashboards/uploads）200
- [x] 定时器恢复（Persistent 补跑 23:32 一轮正常完成）
- [x] 同步基线重置、幂等验证

## 四、遗留与边界

- QA 基础索引的 tg 元数据仍为 9/29 快照口径（检索不依赖 tg；全量重建
  需生产规模 bge-m3 嵌入，按边界未经授权不执行）。
- 老服务（tech-db-fresh 8765/8097、readonly-agent 8766）未动。

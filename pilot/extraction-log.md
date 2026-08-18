# SOFC 提取日志（竖井阶段 1）

日期：2026-08-18
提取对象：SOC/ 下 3 份资产 → pilot/judgments/sofc.json + pilot/signals/sofc.json

## 覆盖率

| 源 | 章节 | 提取结果 |
|---|---|---|
| SOFC行业深度报告 v2.3 | §0/§0.5 | 行业判断（结论+5 条拐点标准+约束性卡点）✅ |
| 同上 | §1 六条路线 | routes 全 6 条 ✅（含 SOEC 边界修正的保留） |
| 同上 | §2 八项指标 | indicators 提取 6 项；净电效率/CHP/可用率/寿命/退化/负荷/冷启动/碳强度中，CHP 总效率与冷启动并入相邻指标未单列 ⚠️ |
| 同上 | §2.5 | 并入 indicators 的 gap_nature 字段 ✅ |
| 同上 | §3 六个卡点 | bottlenecks 全 6 个，标注侧+类型 ✅（5 技术+1 系统） |
| 同上 | §4 共性技术 | cross_domain_tech 5 条 ✅ |
| 同上 | §5 证据账本 | 以 evidence_refs 引用（E01-E14 编号保留），未复制内容 ✅ |
| 同上 | §6 待核实 | to_verify 全 12 条 ✅ |
| 同上 | §7 预警 12 行 | signals 提取 11 条（行 8 系统动态数据与行 11 客户集中已并入；行 12 伙伴退出=负向信号）✅ |
| 专利地图 | 盘点结论 3 条 + 主题分组 | 新增信号 sig-patent-hotspot（专利密度=工程卡点攻关状态证据）；Bloom 数据中心主轴判断并入 bottle-financing-concentration 证据 ⚠️ 部分 |
| SOC知识库_阶段性整理 | SOEC 内容 | **未提取**——主文档明确"SOEC 结论不能写成 SOFC 证据"（§0 修正 1），SOEC 应另立领域树（后续任务）|

## 提取中的判断决定（需要人审）

1. **约束性卡点定为 bottle-opaque-tco（经济/技术侧）**——依据：§0.5 经济性行"当前最大信息缺口不是理论效率，而是全生命周期成本" + §7 中 TCO/寿命数据库两条 🔴。备选：bottle-financing-concentration（系统侧）。两者互为因果（不透明→难融资），选前者因为文档本身把它列为"最大缺口"。
2. **bottle-gas-carbon 归技术侧 economic 而非系统侧**——碳约束的解决者（换燃料/CCUS）是技术开发者自己，符合技术侧定义；政策性碳价并入其拐点条件。
3. **bottle-financing-concentration 归系统侧 ecosystem**——解决者是融资方/客户，非技术开发者。
4. **新增 sig-pcfc-performance**——提取观测时发现高分记录命中不了任何 §7 信号（PCFC 1.44 W/cm²@650℃ 是 route-pcce 的路线级信号），暴露了"信号规格只覆盖卡点、不覆盖路线性能记录"的缺口。这是文档→树提取的第一次反向发现。

## 遇到的 schema 问题（竖井阶段要回答的）

- 指标表 §2 有 8 行，schema 的 indicators 装下 6 项后 CHP/冷启动没有独立节点——指标粒度问题待定（单列 or 并入）
- 专利地图的"数据中心十年三代专利"是强证据但形状不是指标也不是卡点——当前塞进 evidence_refs，是否需要"战略动向"节点类型待定
- 信号关键词匹配的假阳性率可观（sig-carbon-audit 命中 82 条里多数是泛碳话题）——正式版需 embedding + 实体匹配，竖井用 top-N 按分数截断缓解

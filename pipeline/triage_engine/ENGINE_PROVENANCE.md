# 引擎溯源（vendored copy — 请勿在本仓库内修改引擎逻辑）

- 上游仓库：https://github.com/wodewoping-png/triage_engine
- 上游版本：v1.11（直评口径：入域直接 高/中/低，域外不评分）
- 上游提交：a00706e96354ab36255afdfedd9a8fe1e3321012
- 引入日期：2026-09-28
- 引入位置：tech-boundary-db/pipeline/triage_engine/
- 适配层：pipeline/engine_triage.py（唯一允许与引擎对接的模块）
- LLM 复核层 .env 只写仓库级 pipeline/.env（G10，2026-10-02 起）；
  本 vendored 目录零写入——旧版曾写在 triage_engine/.env，已由适配层
  一次性迁移（键合并后删除），引擎目录保持与上游解包一致。
- 集成方只做：行记录构造（lite 记录 → 引擎行 schema）、子进程调用、
  结果字段映射（引擎域→主库 125 叶、展示链→tg 标签、S8 档位→aip 精选）。
  引擎本体的规则/评分/展示链代码零改动。

## 与上游版本对应的功能口径
- 领域判定：语义 GT/AI 叶 + 12 规则域 + 26 扩展域 + 域外（v1.04 语义裁决）
- 载体/类型：T01–T25，C-T16 DOI×语义共决（v1.10），展示链 v1.09
- 评分：类型专属卡 S4 Σ → TRL 加权 → Gate → S8 档位（≥75 高 ≥55 中 <55 低）
- v1.11 直评：入域直接高/中/低；域外不评分（scoreBand=未评分仅为后台状态）
- 参考区/待定等旧最终结果标签已停用（refZone/manual 恒 0 审计位）

# 门户问答部署口径（问题A 收口说明，2026-10-01）

## 结论

**代码迁移已完成且经验证；用户看到的「还是老的」= 生产容器镜像未更新。**

## 证据链

1. **代码侧（本分支）**：门户前端 `web/breadth` 与 `web/` 的问答入口走
   `POST /api/assistant/stream`（agent_service.stream_agent_response）→
   canonical-qa `search_canonical_raw` + citations/claim-check + SSE。
   旧 `/api/assistant/query`（Hermes bridge 直答）已非问答主路径。
2. **生产容器（只读核验，2026-10-01）**：
   - api :0801 容器在跑，`/api/assistant/stream` 存在（未带 token 时 401）；
   - canonical-qa :0801（8767）索引 24,091 条（旧基础快照）+ 726 增量；
   - readonly-agent :0801（8766）= tech-db 旧服务（仅 /health /query），
     仅作对照基准，问答不经过它。
3. **「肉眼看到的还是老的」的定位**：用户访问的门户实例加载的
   web/:0801 镜像与 api/:0801 镜像早于一~六节全部修复
   （见 wu7-image-and-ci.md 镜像审计：:1001 缺 四/五/六）。
   候选镜像 :1002 已构建并隔离冒烟（PR #8 表格），**切换生产需授权**。

## 切换后如何自证不是旧链路

- `/api/stats` 返回 `content_fingerprint`（:1002 新增；:0801 无此字段）；
- 检索 trace 出现 `semantic_graph_degraded` 字段口径（四）；
- 门户问答引用卡走 SSE `citations` 事件（含 claim-check 状态）。

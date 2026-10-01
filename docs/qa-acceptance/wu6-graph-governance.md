# 六.5 图谱治理 —— 审计与隔离验收记录（2026-10-01）

## 结论速览

| 项 | 状态 | 证据 |
|---|---|---|
| 增量共现按记录去重（缺陷已复现+已修复） | 已修复并验证 | 真实 live 索引审计：旧代码单条 94-chunk 记录伪造 3 条「共现94次」边；修复后移除（436→433 边），度数修正（通用技术 210→117 等）。单测 4 项固化 |
| 静态图按版本/墓碑移除旧节点关系 | 已修复（逻辑级验证） | `prune_static_by_ops` 读取侧剪枝：entity_to_records 下标 → record_key_sha 绑定，墓碑/遮蔽证据全灭的节点与边移除；单测 4 项。服务接线（`_governed_static` 缓存 + `_merged_graph` 过滤 + `/api/graph` 透出 static_governance）通过 host 导入检查 |
| 证据定位 | 已修复并验证 | 碎片侧每记录 1 条（此前每 chunk 1 条）；静态侧存活记录证据（records, rid=lite:下标）随剪枝附加 |
| 图↔lite 版本错位防护 | 已修复并验证 | entity_to_records 下标越界 → bound=False + reason，不猜测；单测 1 项 |
| 隔离小样本离线 A 更新/B 删除/C 新增 | 已修复并验证 | backend/tests/test_graph_governance.py 10/10 通过（host, exit 0） |

## 已复现缺陷（真实数据）

live 增量索引（container 卷 techdb_qa_incremental_0801，index.pkl 2026-10-01 01:00）：
509 chunk → 416 唯一记录，其中 1 条上传记录被切 94 chunk。
旧 build_fragment（二.5 版，git HEAD 6ae0ff7）按 chunk 计数：

- 该单条记录自身实体对被累加到 count=94，伪造 3 条边：
  （上传资料, 医学&生物学 / 通用技术 / 基础学科）标签「共现94次」
- chunk 级度数膨胀：上传资料 94（实为 1 条记录）、通用技术 210→117、
  基础学科 146→53、医学&生物学 143→50
- 对照脚本：/tmp/gov/compare.py（旧模块自 git show HEAD 提取，同一份
  meta 双跑对比）；结论输出见下「审计输出」

## 修复内容

- services/canonical-qa/qa-backend/graph_fragment.py
  - `record_group_id`/`_iter_record_groups`：按 chunk_metadata
    record_id > record_key_sha > document_id > key 分组（与 sync/导入/
    上传链身份字段对齐；兜底退化为逐 chunk = 旧行为，不会更差）
  - `build_fragment`：实体抽取/共现累加/度数/证据每记录一次；
    共现窗口（前 5 实体）与阈值（>=2）语义与管线侧一致
  - `prune_static_by_ops`：静态图读取侧治理（墓碑 ∪ 两级替换遮蔽），
    完整性闸门（下标越界→bound=False）
- services/canonical-qa/qa-backend/server.py
  - `_masked_key_shas`：墓碑 ∪ superseded(pending∪landed) 全量身份集
  - `_governed_static`：按（图文件指纹, 墓碑数, 两级遮蔽数, lite 长度）
    缓存的治理视图；lite 不可用时跳过并打日志（检索侧另有
    `_result_allowed` 屏蔽兜底）
  - `_merged_graph`：SEMANTIC_GRAPH 召回用静态标签/邻接先滤掉被移除
    节点及其邻接（被删/被替换记录的实体不再参与实体匹配与邻居扩展）
  - `/api/graph`：返回 `static_governance` 计数，静态节点附存活记录证据

## 验证

```
python3 -m pytest backend/tests/test_graph_governance.py -q
# 10 passed in 0.03s (exit 0) —— 隔离小样本，离线，无模型/索引依赖
python3 /tmp/gov/compare.py
# OLD: nodes=912 edges=436 / NEW: nodes=912 edges=433
# edges removed by per-record dedup: 3（全部为「共现94次」伪造边）
# fragment_signature unchanged: True（缓存失效机制行为不变）
```

## 边界与未验证项

- 服务接线（server.py）为 host 导入级验证（`import server` 因 host 缺
  lightrag 依赖不可行，改由 py_compile + 隔离模块测试覆盖；容器内完整
  导入与真实 HTTP 验收被 0801 旧镜像阻塞——镜像只含 5 个 qa-backend
  模块，无 graph_fragment/record_ops/answer_chain 等，属 七.1 烤镜像
  范围，见 blocker 清单）。
- 静态边 label（共现N次）为整图聚合值、无逐记录明细：部分遮蔽的边
  保守保留原 label（governance.trimmed_nodes 透出），不做无法成立的
  重量化。
- 本审计未改动任何生产向量资产/索引（只读 docker cp 副本 /tmp/gov）。

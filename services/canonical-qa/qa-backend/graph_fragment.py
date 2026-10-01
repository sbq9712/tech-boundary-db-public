#!/usr/bin/env python3
"""增量索引 → 知识图谱实时碎片（集成修复二.5，2026-09-30）。

缺陷：ZIP/逐行导入链只调用向量/BM25 upsert/delete，导入记录从不进入
图谱——/api/graph 与 SEMANTIC_GRAPH 召回只覆盖管线发布的 graph-export.json。

本模块从 canonical-qa 增量索引（上传资料 + 管线同步 chunk）的存活 meta
【实时推导】图谱碎片：实体抽取逻辑与 pipeline/scripts/build_graph_export.py
逐字同源（同一实体空间，同名实体与管线图自然合并），共现关系同规则
（同记录内实体两两成边，count>=2 保留）。因为碎片永远由索引当前内容
推导：record-mutate 更新/删除与 /api/index/delete 物理移除 chunk 后，
对应实体贡献自动消失——不需要（也不允许）单独维护一条变异路径。

每个实体节点附 records（证据定位，最多 3 条）：标题/链接/日期/统一记录
身份（stable_record_id 或 upload key）——「来源记录 + 证据定位」。

六.5（2026-10-01）治理补齐：
- 共现/度数/证据按【记录】而非 chunk 去重——修复前单记录多 chunk 会把
  自身实体对重复累加，跨过 count>=2 阈值伪造「共现N次」边（隔离复现）；
  现按 chunk_metadata 身份（record_id > record_key_sha > document_id >
  key）分组，每记录只计一次，与管线侧逐记录计数语义对齐；
- prune_static_by_ops：静态 graph-export.json 由管线整图重建，运行期
  record-mutate（墓碑/替换遮蔽）不反映在已发布图里——读取侧把
  entity_to_records 下标绑定回 record_key_sha，证据全灭的节点与关联边
  移除、部分遮蔽的节点 degree 降为存活记录数并附存活证据。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

# 与 build_graph_export.py 逐字对齐的抽取规则（勿单独改动一边）
_ORG_RE = re.compile(
    r"([一-鿿]{2,8}(?:大学|学院|研究院|研究所|实验室|公司|集团|企业|科技|能源|动力|电池|材料|化工|制药|生物|半导体|芯片|汽车|航空|航天))")
_EN_ORG_VERB_RE = re.compile(
    r"([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]+){0,3})\s*(?:称|公布|研发|推出|宣布|开发|研制|建成|实现)")
_EN_ORG_STANDALONE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b")
_TECH_RE = re.compile(
    r"([一-鿿]*(?:电池|电池组|太阳能|燃料电池|电解|催化|合成|材料|聚合物|半导体|芯片|量子|超导|纳米|生物|基因|储能|氢能|核聚变|碳捕获|碳循环))")
_NONAME = ("the", "this", "that", "new", "best")


def extract_entities(record: dict) -> set[tuple[str, str]]:
    """从记录字段抽实体，返回 {(类型, 名称)}。字段与 lite/chunk meta 同形：
    t 标题 / as 摘要 / b 正文 / kp 关键参数 / a 来源 / c 分类。"""
    title = record.get("t", "") or ""
    summary = record.get("as", "") or ""
    body = record.get("b", "") or ""
    key_params = record.get("kp", [])
    if not isinstance(key_params, list):
        key_params = []
    source = record.get("a", "") or record.get("s", "") or ""
    category = record.get("c", "") or ""

    entities: set[tuple[str, str]] = set()

    # 1. 来源机构
    src = str(source).strip()
    if 2 <= len(src) <= 50:
        entities.add(("机构", src))

    # 2. 标题/摘要中的组织名
    text = f"{title} {summary}"
    for m in _ORG_RE.finditer(text):
        entities.add(("机构", m.group(1)))
    for m in _EN_ORG_VERB_RE.finditer(text):
        name = m.group(1).strip()
        if len(name) >= 3:
            entities.add(("公司", name))
    for m in _EN_ORG_STANDALONE_RE.finditer(title):
        name = m.group(1).strip()
        if len(name) >= 4 and name.lower() not in _NONAME:
            entities.add(("公司", name))

    # 3. 关键参数 → 指标 + 条件技术
    for kp in key_params:
        kp_str = str(kp)
        param_name = kp_str.split("[")[0].split(":")[0].strip()
        if param_name and len(param_name) >= 2:
            entities.add(("指标", param_name))
        for cond_match in re.finditer(r"\[([^\]]+)\]", kp_str):
            cond = cond_match.group(1).strip()
            if len(cond) >= 2:
                entities.add(("技术", cond))

    # 4. 分类 → 主题实体
    if category:
        for part in str(category).split("/"):
            part = part.strip()
            if part and len(part) >= 2:
                entities.add(("分类", part))

    # 5. 标题中的技术关键词
    for m in _TECH_RE.finditer(title):
        tech = m.group(1)
        if len(tech) >= 3:
            entities.add(("技术", tech))

    return entities


def record_evidence(meta: dict) -> dict:
    """chunk meta → 证据定位条目（统一记录身份优先）。"""
    md = meta.get("chunk_metadata") or {}
    rid = str(md.get("record_id") or md.get("record_key_sha")
              or meta.get("key") or "")
    return {
        "t": str(meta.get("t", "") or "")[:120],
        "u": str(md.get("url") or meta.get("u") or ""),
        "d": str(md.get("document_date") or meta.get("d") or ""),
        "rid": rid,
        "kind": str(meta.get("kind") or "upload"),
    }


def record_group_id(meta: dict) -> str:
    """chunk 的所属记录身份（六.5 逐记录去重的分组键）。

    优先级与 sync/导入链的身份字段对齐：
    chunk_metadata.record_id（管线 stable_record_id）
    > chunk_metadata.record_key_sha（一.3 统一身份，导入/同步链）
    > chunk_metadata.document_id / meta.document_id（上传链：一文档一记录）
    > meta.key（upload:{document_id}:{chunk} —— 兜底退化为逐 chunk，
      与修复前行为一致，不会更差）。"""
    md = meta.get("chunk_metadata") or {}
    return str(md.get("record_id") or md.get("record_key_sha")
               or md.get("document_id") or meta.get("document_id")
               or meta.get("key") or "")


def _iter_record_groups(meta_rows: list[dict]):
    """按记录身份分组 chunk meta；保持首次出现顺序。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for meta in meta_rows:
        groups[record_group_id(meta)].append(meta)
    return groups


def build_fragment(meta_rows: list[dict]) -> dict:
    """由增量索引存活 meta 构建碎片（六.5：逐记录去重）。

    返回 {"nodes": [...], "edges": [...]}，与 graph-export.json 同构
    （nodes: id/label/type/description/degree [+records]；
      edges: source/target/label 共现N次）。

    修复前（二.5）逐 chunk 计数：同一记录的多个 chunk 会把自身实体对
    重复累加——单记录 2 chunk 即可把仅出现一次的共现抬高到 count=2，
    跨过阈值伪造「共现2次」边；degree/证据也按 chunk 膨胀。现按
    record_group_id 分组：实体抽取、共现累加、度数、证据每记录一次，
    与管线侧（逐记录 entity_to_records.append）语义对齐。"""
    entity_records: dict[str, list[str]] = defaultdict(list)
    entity_types: dict[str, str] = {}
    entity_descs: dict[str, list[str]] = defaultdict(list)
    entity_evidence: dict[str, list[dict]] = defaultdict(list)
    edge_count: dict[tuple[str, str], int] = defaultdict(int)

    for rid, rows in _iter_record_groups(meta_rows).items():
        # 同记录多 chunk：字段取首个非空（t/as/a/s/c 在 chunk 间是复制的），
        # kp 取并集（同为复制），b/fb 逐 chunk 拼接（抽取不依赖正文，仅为忠实）
        rec: dict = {}
        for field in ("t", "as", "a", "s", "c"):
            rec[field] = next((m.get(field) for m in rows if m.get(field)), "")
        rec["a"] = rec["a"] or rec["s"]
        kp: list = []
        body_parts: list[str] = []
        for m in rows:
            md = m.get("chunk_metadata") or {}
            cand = md.get("kp")
            if isinstance(cand, list):
                for k in cand:
                    if k not in kp:
                        kp.append(k)
            body = m.get("b") or m.get("fb") or ""
            if body:
                body_parts.append(str(body))
        rec["kp"] = kp
        rec["b"] = "\n".join(body_parts)

        pairs = extract_entities(rec)
        if not pairs:
            continue
        ev = record_evidence(rows[0])
        uniq = list(dict.fromkeys(name for _etype, name in pairs))
        for etype, name in pairs:
            # 类型首个胜出（与管线侧 entity_types.setdefault 语义一致）
            entity_types.setdefault(name, etype)
        for name in uniq:
            entity_records[name].append(rid)
            entity_evidence[name].append(ev)
            if len(entity_descs[name]) < 2:
                t = str(rec.get("t") or "")[:100]
                if t:
                    entity_descs[name].append(t)
        for i in range(len(uniq)):
            for j in range(i + 1, min(i + 5, len(uniq))):
                # 逐【记录】累加一次（与管线侧一致）；窗口=前5个实体（同管线）
                pair = tuple(sorted((uniq[i], uniq[j])))
                edge_count[pair] += 1

    nodes = []
    for name, rids in entity_records.items():
        nodes.append({
            "id": name,
            "label": name,
            "type": entity_types.get(name, "概念"),
            "description": "; ".join(entity_descs[name][:2]),
            "degree": len(rids),
            # 证据定位（增量字段：门户旧渲染忽略；检索侧 evidence 直接可用）
            "records": entity_evidence[name][:3],
        })
    edges = [
        {"source": src, "target": tgt, "label": f"共现{count}次"}
        for (src, tgt), count in edge_count.items()
        if count >= 2 and src != tgt
    ]
    return {"nodes": nodes, "edges": edges}


def merge_into_static(static: dict, fragment: dict, max_records: int = 3) -> dict:
    """把碎片合并进静态 graph-export.json 结构（/api/graph 与 _graph_index 共用）。

    同名节点（同一实体空间）：degree 累加、description 追加（去重截断）、
    records 优先碎片证据；边按 (source,target) 计数合并。返回新 dict，不改入参。"""
    nodes = {str(n.get("id")): dict(n) for n in (static.get("nodes") or [])}
    for fn in fragment.get("nodes") or []:
        fid = str(fn["id"])
        base = nodes.get(fid)
        if base is None:
            nodes[fid] = dict(fn)
            continue
        base["degree"] = int(base.get("degree") or 0) + int(fn.get("degree") or 0)
        merged_desc = str(base.get("description") or "")
        extra = str(fn.get("description") or "")
        if extra and extra not in merged_desc:
            merged_desc = f"{merged_desc}; {extra}"[:220]
            base["description"] = merged_desc
        base["records"] = (fn.get("records") or [])[:max_records]
    edges: dict[tuple[str, str], dict] = {}
    for e in static.get("edges") or []:
        edges[(str(e.get("source")), str(e.get("target")))] = dict(e)
    for e in fragment.get("edges") or []:
        key = (str(e.get("source")), str(e.get("target")))
        if key in edges:
            try:
                old = int(str(edges[key].get("label", "")).replace("共现", "").replace("次", "") or 0)
            except ValueError:
                old = 0
            new = old + int(str(e.get("label", "")).replace("共现", "").replace("次", "") or 0)
            edges[key]["label"] = f"共现{new}次"
        else:
            edges[key] = dict(e)
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def prune_static_by_ops(static: dict, records: list, sha_of, masked,
                        max_records: int = 3) -> dict:
    """静态图按版本/墓碑治理（六.5，读取侧剪枝）。

    graph-export.json 由管线整图重建：发布之后的运行期 record-mutate
    delete/update（持久化墓碑 + 基础索引替换遮蔽）不会反映进已发布图，
    已删除/已被新版本取代的记录实体仍出现在 /api/graph 与 SEMANTIC_GRAPH
    召回扩展里（记录本身的检索屏蔽在 server._result_allowed 已生效，这里
    治理的是图谱层的残留可见性/影响）。

    做法：entity_to_records（实体 → 图构建时 lite 数组下标）绑定回记录
    身份 record_key_sha = sha_of(t, d, u)：
    - 证据全部被遮蔽 → 节点及其全部关联边移除；
    - 部分被遮蔽 → 节点保留，degree 降为存活记录数，并附存活记录证据
      （records，最多 max_records 条，与碎片侧证据定位同构）；
    - entity_to_records 缺失/不可解析（旧版图文件）→ 无法可靠绑定，
      原样保留全部节点并在 governance.bound=False 中说明，不做猜测。

    边的 weight 是整图聚合值、无逐记录明细，部分遮蔽的边保留原 label
    （保守不过估），governance.trimmed_nodes 透出受影响计数。

    返回与输入同构的 dict，附 "governance" 字段：
    {"bound": bool, "dropped_nodes": int, "trimmed_nodes": int,
     "unbound_nodes": int, "dropped_node_ids": [...], "dropped_labels": [...]}
    """
    nodes_in = static.get("nodes") or []
    e2r = static.get("entity_to_records")
    out = {k: v for k, v in static.items()
           if k not in ("nodes", "edges", "entity_to_records")}
    edges_in = [dict(e) for e in (static.get("edges") or [])]
    if not isinstance(e2r, dict):
        out.update({
            "nodes": [dict(n) for n in nodes_in],
            "edges": edges_in,
            "governance": {"bound": False, "dropped_nodes": 0,
                           "trimmed_nodes": 0, "unbound_nodes": len(nodes_in),
                           "dropped_node_ids": [], "dropped_labels": []},
        })
        return out

    n = len(records) if isinstance(records, list) else 0
    # 完整性闸门：图引用的 lite 下标越界 = 图与 lite 版本错位（不同发布轮），
    # 绑定不可靠 → 不猜测，原样保留（与无绑定同路径，bound=False 说明原因）
    max_idx = -1
    for idxs in e2r.values():
        if isinstance(idxs, list) and idxs:
            try:
                max_idx = max(max_idx, max(int(i) for i in idxs))
            except (TypeError, ValueError):
                continue
    if max_idx >= n:
        out.update({
            "nodes": [dict(x) for x in nodes_in],
            "edges": edges_in,
            "governance": {"bound": False, "dropped_nodes": 0,
                           "trimmed_nodes": 0, "unbound_nodes": len(nodes_in),
                           "dropped_node_ids": [], "dropped_labels": [],
                           "reason": (f"entity_to_records max index {max_idx} "
                                      f">= lite records {n}; graph/lite "
                                      f"version mismatch")},
        })
        return out
    masked = {str(m) for m in (masked or set())}
    kept: dict[str, dict] = {}
    new_e2r: dict[str, list] = {}
    dropped_ids: list[str] = []
    dropped_labels: list[str] = []
    dropped = trimmed = unbound = 0
    # 四：端点存活成员集合（边贡献可验证性判定用）
    kshas_by_node: dict[str, set] = {}
    members_changed: set[str] = set()

    for node in nodes_in:
        nid = str(node.get("id"))
        idxs = e2r.get(nid)
        if not isinstance(idxs, list):
            # 无法绑定到记录身份 → 不猜测，原样保留并计数
            unbound += 1
            kept[nid] = dict(node)
            continue
        alive = []
        for i in idxs:
            try:
                iv = int(i)
            except (TypeError, ValueError):
                continue
            if not (0 <= iv < n):
                continue
            rec = records[iv] if isinstance(records[iv], dict) else {}
            if str(sha_of(rec.get("t", ""), rec.get("d", ""),
                          rec.get("u", ""))) in masked:
                continue
            alive.append(iv)
        if not alive:
            dropped += 1
            dropped_ids.append(nid)
            dropped_labels.append(str(node.get("label") or nid))
            continue
        out_node = dict(node)
        if len(alive) != len(idxs):
            trimmed += 1
            members_changed.add(nid)
            out_node["degree"] = len(alive)
        out_node["records"] = [{
            "t": str(records[i].get("t", ""))[:120],
            "u": str(records[i].get("u", "")),
            "d": str(records[i].get("d", "")),
            "rid": f"lite:{i}",
            "kind": "pipeline",
        } for i in alive[:max_records]]
        # 四：节点级贡献清单（存活记录身份）——边贡献可验证性的基础
        out_node["source_kshas"] = [
            str(sha_of(records[i].get("t", ""), records[i].get("d", ""),
                       records[i].get("u", ""))) for i in alive]
        kept[nid] = out_node
        new_e2r[nid] = alive
        kshas_by_node[nid] = set(out_node["source_kshas"])

    # 四：边贡献可验证性。静态导出的边 weight 是整图聚合共现值、无逐记录
    # 明细——端点被裁剪（墓碑/替换）后，原 weight 可能全部/部分来自已消失
    # 的记录对。未验证的聚合值不得原样保留：
    # - 任一端点 members_changed（存活集合 != 原集合）→ weight 未验证，
    #   置 0 并标记 weight_unverified（拓扑保留，供可视；不作为证据权重）；
    # - 端点无成员变化 → weight 与图构建输入一致，weight_unverified=False。
    # 共现关系（co-occurrence，本导出全部如此）与事实关系（factual，带
    # 逐记录证据，本导出暂无）以此字段区分，消费方不得混用。
    new_edges = []
    edges_unverified = 0
    for e in edges_in:
        src, dst = str(e.get("source")), str(e.get("target"))
        if src not in kept or dst not in kept:
            continue
        out_edge = dict(e)
        src_changed = src in members_changed
        dst_changed = dst in members_changed
        if src_changed or dst_changed:
            out_edge["weight"] = 0
            out_edge["weight_unverified"] = True
            out_edge["relation_kind"] = "co_occurrence_aggregate"
            edges_unverified += 1
        else:
            out_edge["weight_unverified"] = False
            out_edge["relation_kind"] = "co_occurrence_aggregate"
        new_edges.append(out_edge)

    out.update({
        "nodes": list(kept.values()),
        "edges": new_edges,
        "entity_to_records": new_e2r,
        "governance": {"bound": True, "dropped_nodes": dropped,
                       "trimmed_nodes": trimmed, "unbound_nodes": unbound,
                       "edges_unverified": edges_unverified,
                       "dropped_node_ids": dropped_ids,
                       "dropped_labels": dropped_labels},
    })
    return out


def fragment_signature(meta_rows: list[dict]) -> str:
    """碎片输入指纹：len + 各 chunk key 拼接哈希——脏检查用。"""
    import hashlib
    h = hashlib.sha256()
    h.update(str(len(meta_rows)).encode())
    for meta in meta_rows:
        h.update(str(meta.get("key") or "").encode())
        h.update(str(meta.get("checksum") or "").encode())
    return h.hexdigest()[:16]


def load_static_graph(working_dir: Path) -> dict:
    graph_file = working_dir / "graph-export.json"
    if graph_file.exists():
        try:
            return json.loads(graph_file.read_text("utf-8"))
        except (ValueError, OSError):
            return {}
    return {}

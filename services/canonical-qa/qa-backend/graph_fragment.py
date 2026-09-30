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
    rid = str(md.get("record_id") or meta.get("key") or "")
    return {
        "t": str(meta.get("t", "") or "")[:120],
        "u": str(md.get("url") or meta.get("u") or ""),
        "d": str(md.get("document_date") or meta.get("d") or ""),
        "rid": rid,
        "kind": str(meta.get("kind") or "upload"),
    }


def build_fragment(meta_rows: list[dict]) -> dict:
    """由增量索引存活 meta 构建碎片。

    返回 {"nodes": [...], "edges": [...]}，与 graph-export.json 同构
    （nodes: id/label/type/description/degree [+records]；
      edges: source/target/label 共现N次）。"""
    entity_records: dict[str, list[str]] = defaultdict(list)
    entity_types: dict[str, str] = {}
    entity_descs: dict[str, list[str]] = defaultdict(list)
    entity_evidence: dict[str, list[dict]] = defaultdict(list)
    edge_count: dict[tuple[str, str], int] = defaultdict(int)

    for meta in meta_rows:
        md = meta.get("chunk_metadata") or {}
        rec = {
            "t": meta.get("t", ""),
            "as": meta.get("as", ""),
            "b": meta.get("b", "") or meta.get("fb", "") or "",
            "kp": md.get("kp") or [],
            "a": meta.get("a", "") or meta.get("s", "") or "",
            "c": meta.get("c", "") or "",
        }
        names = [name for _etype, name in extract_entities(rec)]
        if not names:
            continue
        pairs = extract_entities(rec)
        ev = record_evidence(meta)
        uniq = list(dict.fromkeys(names))
        for etype, name in pairs:
            # 类型首个胜出（与管线侧 entity_types.setdefault 语义一致）
            entity_types.setdefault(name, etype)
        for name in uniq:
            entity_records[name].append(str(meta.get("key") or ""))
            entity_evidence[name].append(ev)
            if len(entity_descs[name]) < 2:
                t = str(rec.get("t") or "")[:100]
                if t:
                    entity_descs[name].append(t)
        for i in range(len(uniq)):
            for j in range(i + 1, min(i + 5, len(uniq))):
                # 逐记录累加（与管线侧一致）；窗口=前5个实体（同管线）
                pair = tuple(sorted((uniq[i], uniq[j])))
                edge_count[pair] += 1

    nodes = []
    for name, keys in entity_records.items():
        nodes.append({
            "id": name,
            "label": name,
            "type": entity_types.get(name, "概念"),
            "description": "; ".join(entity_descs[name][:2]),
            "degree": len(keys),
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

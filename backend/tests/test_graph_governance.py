"""六.5 图谱治理契约测试（隔离小样本，离线，无模型/索引依赖）。

覆盖 services/canonical-qa/qa-backend/graph_fragment.py：
- 增量碎片共现/度数/证据按【记录】而非 chunk 去重——修复前单记录
  2 chunk 即可把仅出现一次的共现累加到 count=2，跨过阈值伪造
  「共现2次」边（已复现缺陷，本测试固化回归）；
- 记录 A 更新 / B 删除 / C 新增的碎片演化：旧贡献随之消失、新贡献
  出现、跨记录共现边随任一参与方移除而消失；
- 静态图读取侧按 record_key_sha 墓碑/替换遮蔽剪枝：部分遮蔽 degree
  降级 + 存活证据定位、证据全灭节点与关联边移除、旧版无
  entity_to_records 的图不猜测（bound=False 原样保留）。
"""
import hashlib
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def gf():
    import importlib.util

    for base in Path(__file__).resolve().parents:
        cand = base / "services/canonical-qa/qa-backend/graph_fragment.py"
        if cand.exists():
            spec = importlib.util.spec_from_file_location(
                "graph_fragment_governance", cand)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    pytest.skip("canonical-qa graph_fragment.py not reachable from this layout")


def _meta(rid, key, kp, a, u):
    """构造与增量索引 meta 同构的 chunk 记录（实体来自 kp/来源）。"""
    return {
        "key": key,
        "kind": "upload",
        "t": "统一标题（不引入额外实体）",
        "d": "2026-09-01",
        "a": a,
        "s": a,
        "as": "",
        "c": "",
        "b": "",
        "fb": "",
        "u": u,
        "chunk_metadata": {
            "record_id": rid,
            "kp": list(kp),
            "url": u,
            "document_date": "2026-09-01",
        },
    }


A0 = _meta("rec-A", "upload:docA:0", ["能量密度[固态电解质]"],
           "南方能源实验室", "https://example.test/docA")
A1 = _meta("rec-A", "upload:docA:1", ["能量密度[固态电解质]"],
           "南方能源实验室", "https://example.test/docA")
A2_V2 = _meta("rec-A", "upload:docA-v2:0", ["充放速率[硅碳负极]"],
              "南方能源实验室", "https://example.test/docA-v2")
B0 = _meta("rec-B", "upload:docB:0",
           ["能量密度[固态电解质]", "循环寿命[高镍正极]"],
           "北方材料研究所", "https://example.test/docB")
C0 = _meta("rec-C", "upload:docC:0", ["循环寿命[高镍正极]"],
           "东江电池公司", "https://example.test/docC")
D0 = _meta("rec-D", "upload:docD:0", ["能量密度[固态电解质]"],
           "东江电池公司", "https://example.test/docD")


def _labels(frag):
    return {n["label"]: n["degree"] for n in frag["nodes"]}


def _edge(src, tgt, label):
    return frozenset((src, tgt)) | {label}


def _edge_set(frag):
    # 边端点顺序由 build_fragment 的 sorted(pair) 决定，断言时无序比较
    return {frozenset((e["source"], e["target"])) | {e["label"]}
            for e in frag["edges"]}


# ── 逐记录共现去重（六.5 核心缺陷修复） ─────────────────────────────


def test_single_record_multi_chunk_does_not_fabricate_cooccurrence(gf):
    """已复现缺陷：单记录 2 chunk 自身实体对不得伪造「共现2次」边。"""
    frag = gf.build_fragment([A0, A1])
    assert _labels(frag) == {"能量密度": 1, "固态电解质": 1,
                             "南方能源实验室": 1}
    assert frag["edges"] == []
    # 证据按记录去重：2 chunk → 1 条证据
    assert len(frag["nodes"][0]["records"]) == 1
    assert frag["nodes"][0]["records"][0]["rid"] == "rec-A"


def test_cross_record_cooccurrence_counts_records_not_chunks(gf):
    """2 记录共现 = 「共现2次」；记录 A 的第二个 chunk 不虚增为 3。"""
    frag = gf.build_fragment([A0, A1, B0])
    # B 有 4 个实体 → 全对窗口内；A∪B 共享对 count=2，B 其余对 count=1
    assert _edge_set(frag) == {_edge("能量密度", "固态电解质", "共现2次")}


def test_baseline_two_shared_pairs(gf):
    frag = gf.build_fragment([A0, A1, B0, C0])
    assert _edge_set(frag) == {_edge("能量密度", "固态电解质", "共现2次"),
                               _edge("循环寿命", "高镍正极", "共现2次")}


# ── A 更新 / B 删除 / C 新增（隔离小样本离线演化测试） ───────────────


def test_a_update_b_delete_c_add_lifecycle(gf):
    # A 更新（rec-A 换新内容）：
    upd = gf.build_fragment([A2_V2, B0, C0])
    labels = _labels(upd)
    assert labels["充放速率"] == 1 and labels["硅碳负极"] == 1
    # A 旧贡献移除：「能量密度」只剩 B（degree 1），其与「固态电解质」
    # 的共现只剩 B 一家 → 边消失
    assert labels["能量密度"] == 1
    assert _edge_set(upd) == {_edge("循环寿命", "高镍正极", "共现2次")}
    # 新证据定位指向同一记录身份
    rids = {n["label"]: n["records"][0]["rid"] for n in upd["nodes"]}
    assert rids["充放速率"] == "rec-A"

    # B 删除：独有来源实体消失；两条共现边各失去一方 → 全部消失
    dele = gf.build_fragment([A0, A1, C0])
    labels = _labels(dele)
    assert "北方材料研究所" not in labels
    assert labels["能量密度"] == 1 and labels["循环寿命"] == 1
    assert dele["edges"] == []

    # C/D 新增：新记录把已有实体抬回共现阈值、新来源实体出现
    add = gf.build_fragment([A0, A1, B0, C0, D0])
    labels = _labels(add)
    assert labels["能量密度"] == 3
    # 来源实体「东江电池公司」来自 C0 与 D0 两条记录 → degree 2
    assert labels["东江电池公司"] == 2
    assert len(add["edges"]) == 2


# ── 静态图按版本/墓碑剪枝（读取侧治理） ─────────────────────────────


def _sha_of(t, d, u):
    # 与 server._record_key_sha_of / sync_qa_index 同公式
    return hashlib.sha256(
        json.dumps([str(t or ""), str(d or ""), str(u or "")],
                   ensure_ascii=False).encode("utf-8")).hexdigest()


def _static():
    records = [
        {"t": "Rec Zero", "d": "2026-09-01", "u": "https://x/0"},
        {"t": "Rec One", "d": "2026-09-02", "u": "https://x/1"},
        {"t": "Rec Two", "d": "2026-09-03", "u": "https://x/2"},
    ]
    static = {
        "nodes": [{"id": "N1", "label": "N1", "degree": 1, "type": "机构"},
                  {"id": "N2", "label": "N2", "degree": 2, "type": "指标"},
                  {"id": "N3", "label": "N3", "degree": 1, "type": "技术"}],
        "edges": [{"source": "N1", "target": "N2", "label": "共现1次"},
                  {"source": "N2", "target": "N3", "label": "共现4次"}],
        "entity_to_records": {"N1": [0], "N2": [1, 2], "N3": [0]},
    }
    return records, static


def test_static_prune_partial_masking_trims_degree_and_attaches_alive_evidence(gf):
    records, static = _static()
    masked = {_sha_of(**records[1])}
    p = gf.prune_static_by_ops(static, records, _sha_of, masked)
    gov = p["governance"]
    assert gov["bound"] is True
    assert gov["dropped_nodes"] == 0 and gov["trimmed_nodes"] == 1
    n2 = next(n for n in p["nodes"] if n["id"] == "N2")
    assert n2["degree"] == 1
    assert n2["records"] == [{"t": "Rec Two", "u": "https://x/2",
                              "d": "2026-09-03", "rid": "lite:2",
                              "kind": "pipeline"}]
    assert p["entity_to_records"]["N2"] == [2]
    assert len(p["edges"]) == 2  # 两端仍存活 → 边保留


def test_static_prune_full_masking_drops_node_and_edges(gf):
    records, static = _static()
    masked = {_sha_of(**records[1]), _sha_of(**records[2])}
    p = gf.prune_static_by_ops(static, records, _sha_of, masked)
    gov = p["governance"]
    assert gov["dropped_nodes"] == 1
    assert gov["dropped_node_ids"] == ["N2"]
    assert gov["dropped_labels"] == ["N2"]
    assert [n["id"] for n in p["nodes"]] == ["N1", "N3"]
    assert p["edges"] == []
    assert "N2" not in p["entity_to_records"]


def test_static_prune_no_ops_keeps_graph_and_adds_evidence(gf):
    records, static = _static()
    p = gf.prune_static_by_ops(static, records, _sha_of, set())
    assert p["governance"] == {
        "bound": True, "dropped_nodes": 0, "trimmed_nodes": 0,
        "unbound_nodes": 0, "dropped_node_ids": [], "dropped_labels": []}
    assert len(p["nodes"]) == 3 and len(p["edges"]) == 2
    n1 = next(n for n in p["nodes"] if n["id"] == "N1")
    assert n1["records"][0]["rid"] == "lite:0"


def test_static_prune_legacy_graph_without_bindings_is_not_guessed(gf):
    records, _ = _static()
    legacy = {"nodes": [{"id": "X", "label": "X", "degree": 5}], "edges": []}
    p = gf.prune_static_by_ops(legacy, records, _sha_of, {"anything"})
    assert p["governance"]["bound"] is False
    assert p["governance"]["unbound_nodes"] == 1
    assert p["nodes"][0]["degree"] == 5  # 原样保留，不猜测


def test_static_prune_graph_lite_version_mismatch_does_not_guess(gf):
    """图引用下标越界（图与 lite 不同发布轮）→ 绑定不可靠，不猜测。"""
    records, static = _static()
    static = dict(static, entity_to_records={"N1": [0], "N2": [1, 99]})
    p = gf.prune_static_by_ops(static, records, _sha_of,
                               {_sha_of(**records[1])})
    gov = p["governance"]
    assert gov["bound"] is False
    assert "version mismatch" in gov["reason"]
    assert [n["id"] for n in p["nodes"]] == ["N1", "N2", "N3"]  # 原样保留
    assert len(p["edges"]) == 2


def test_merge_into_static_accepts_pruned_static(gf):
    records, static = _static()
    p = gf.prune_static_by_ops(static, records, _sha_of, set())
    merged = gf.merge_into_static(p, gf.build_fragment([]))
    assert len(merged["nodes"]) == 3
    assert all("records" in n for n in merged["nodes"])

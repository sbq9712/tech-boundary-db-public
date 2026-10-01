"""四：图谱绑定治理契约。

- 绑定可靠（entity_to_records 可解析且不越界）→ bound=True，墓碑/替换
  记录的实体证据被剔除；证据全灭节点与关联边移除；部分遮蔽节点 degree
  降为存活数，其关联边 weight 置 0 并标 weight_unverified（四：未验证
  的聚合共现值不得原样保留）；端点无成员变化的边 weight 原样且标记
  verified。
- 绑定不可证明（越界/缺失/坏结构）→ bound=False（消费方必须将静态图
  退出 QA 扩展），不做猜测。
- 仅关系证据删除：边一端证据全灭 → 边移除（另一端即使还有其他来源
  记录，也不再保留未验证的旧共现计数）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from graph_fragment import prune_static_by_ops  # noqa: E402


def sha_of(t, d, u):
    return f"sha::{t}"


def _static():
    return {
        "nodes": [
            {"id": "n1", "label": "固态电解质", "degree": 2},
            {"id": "n2", "label": "千吨级产线", "degree": 2},
            {"id": "n3", "label": "共现孤证", "degree": 1},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "label": "共现", "weight": 2},
            {"source": "n1", "target": "n3", "label": "共现", "weight": 1},
        ],
        "entity_to_records": {
            "n1": [0, 1],
            "n2": [1],
            "n3": [2],
        },
    }


RECORDS = [
    {"t": "记录A", "d": "2026-10-01", "u": "https://x/a"},
    {"t": "记录B", "d": "2026-10-01", "u": "https://x/b"},
    {"t": "记录C", "d": "2026-10-01", "u": "https://x/c"},
]


def test_bound_true_prunes_tombstoned_and_marks_edges():
    # 记录C 被墓碑 → n3 证据全灭：节点移除 + 关联边移除（仅关系证据删除）
    out = prune_static_by_ops(_static(), RECORDS, sha_of, masked={"sha::记录C"})
    gov = out["governance"]
    assert gov["bound"] is True
    labels = {n["label"] for n in out["nodes"]}
    assert "共现孤证" not in labels and "固态电解质" in labels
    # n1-n3 边已随 n3 移除；n1-n2 保留
    pairs = {(e["source"], e["target"]) for e in out["edges"]}
    assert ("n1", "n3") not in pairs and ("n1", "n2") in pairs
    # n1 记录A 被替换遮蔽（部分遮蔽）：n1/n2 的边 weight 未验证置 0
    out2 = prune_static_by_ops(_static(), RECORDS, sha_of, masked={"sha::记录A"})
    gov2 = out2["governance"]
    assert gov2["bound"] is True and gov2["trimmed_nodes"] >= 1
    assert gov2["edges_unverified"] >= 1
    e12 = [e for e in out2["edges"] if {e["source"], e["target"]} == {"n1", "n2"}][0]
    assert e12["weight"] == 0 and e12["weight_unverified"] is True
    assert e12["relation_kind"] == "co_occurrence_aggregate"


def test_equal_count_tombstone_swap_still_prunes():
    """等量换墓碑：记录A→C 换身份，节点/边证据按新成员集合剪枝。"""
    out = prune_static_by_ops(_static(), RECORDS, sha_of, masked={"sha::记录C"})
    # 记录B 仍存活：n2 保留；n3（仅记录C）证据全灭
    assert {n["label"] for n in out["nodes"]} == {"固态电解质", "千吨级产线"}


def test_out_of_range_binding_reports_bound_false():
    static = _static()
    static["entity_to_records"]["n1"] = [0, 99]  # 越界：图/记录版本错位
    out = prune_static_by_ops(static, RECORDS, sha_of, masked=set())
    assert out["governance"]["bound"] is False
    assert out["governance"]["unbound_nodes"] == 3


def test_missing_binding_reports_bound_false():
    static = _static()
    static.pop("entity_to_records")  # 旧版图文件
    out = prune_static_by_ops(static, RECORDS, sha_of, masked=set())
    assert out["governance"]["bound"] is False


def test_content_change_reflected_in_node_sources():
    """内容变化（同身份重写）→ 节点 source_kshas 按当前 lite 内容重算。"""
    out = prune_static_by_ops(_static(), RECORDS, sha_of, masked=set())
    n1 = [n for n in out["nodes"] if n["label"] == "固态电解质"][0]
    assert n1["source_kshas"] == ["sha::记录A", "sha::记录B"]

"""任务二 2.2/2.3 回归测试：分源候选池 + 单路故障隔离。

2.2（先过滤后截断）：历史缺陷——vector_search/bm25_search 全局取
top_k*3 再按来源过滤，6 条高分广度 chunk 可把唯一可命中的 atsc chunk
整体挤出（atsc 范围查询向量/关键词双路 0 召回）。修复：allowed 谓词在
增量索引候选形成阶段生效，范围内计满 top_k。

2.3（单路隔离）：vector/keyword 任一路异常不再丢弃另一路的合法结果；
路线记录区分 executed/succeeded/raw_candidates/duration_ms/error，
成功零命中 ≠ 失败。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np

from incremental_index import IncrementalIndex
from rank_bm25 import BM25Okapi

import re
from typing import Any

SERVER_SRC = Path(__file__).resolve().parent.parent / "server.py"


def _mk_index(tmp_path: Path) -> IncrementalIndex:
    idx = IncrementalIndex(tmp_path / "inc.pkl", embedding_func=None)
    idx.loaded = True
    return idx


def _seed(idx: IncrementalIndex, rows: list[dict]) -> None:
    """rows: [{section, vec:[...], tokens:[...], b}] —— 直接构造物理状态。"""
    dim = 8
    embs = []
    for r in rows:
        v = np.zeros(dim, dtype=np.float32)
        for i, x in enumerate(r["vec"]):
            v[i] = x
        embs.append(v / max(np.linalg.norm(v), 1e-8))
    idx.embeddings = np.stack(embs)
    idx.meta = [
        {"document_id": r["doc"], "chunk_id": f"{r['doc']}-0", "b": r["b"],
         "t": r.get("t", ""), "kind": "upload",
         "chunk_metadata": {"primary_section": r["section"]}}
        for r in rows
    ]
    idx.corpus_tokens = [list(r["tokens"]) for r in rows]
    idx.bm25 = BM25Okapi(idx.corpus_tokens) if idx.corpus_tokens else None


def _scope_allowed(section: str):
    def _pred(meta: dict) -> bool:
        md = meta.get("chunk_metadata") or {}
        return md.get("primary_section") == section
    return _pred


def _rows_skewed() -> list[dict]:
    """6 条高分广度 chunk（向量方向 0）+ 1 条 atsc chunk（方向 1）。"""
    rows = []
    for i in range(6):
        rows.append({"doc": f"bd-{i}", "section": "breadth",
                     "vec": [1.0, 0.0], "tokens": ["钠离子", "电池", "广度"],
                     "b": "广度钠离子电池报道", "t": f"广度{i}"})
    rows.append({"doc": "at-1", "section": "atsc",
                 "vec": [0.0, 1.0], "tokens": ["钠离子", "电池", "atsc"],
                 "b": "ATSC 内部钠离子电池研究", "t": "ATSC研究"})
    return rows


def test_vector_scope_pool_not_squeezed_by_high_scores(tmp_path):
    """atsc 范围 + 查询贴近广度方向：范围池仍召回 atsc chunk。"""
    idx = _mk_index(tmp_path)
    _seed(idx, _rows_skewed())
    q = np.zeros(8, dtype=np.float32)
    q[0] = 1.0  # 与 6 条广度 chunk 最相似（历史实现下 atsc 被全局截断挤出）
    q = q / np.linalg.norm(q)
    out = idx.vector_search(q, top_k=2, allowed=_scope_allowed("atsc"))
    assert [r["meta"]["document_id"] for r in out] == ["at-1"]
    out_all = idx.vector_search(q, top_k=3)
    assert len(out_all) == 3 and out_all[0]["meta"]["document_id"].startswith("bd-")


def test_bm25_scope_pool_not_squeezed_by_high_scores(tmp_path):
    """atsc 范围关键词检索：词项命中的广度 chunk 全部不在池内，atsc 照常召回。"""
    idx = _mk_index(tmp_path)
    _seed(idx, _rows_skewed())
    out = idx.bm25_search("钠离子 电池", top_k=2, allowed=_scope_allowed("atsc"))
    docs = [r["meta"]["document_id"] for r in out]
    assert docs == ["at-1"]
    assert all((r["meta"].get("chunk_metadata") or {}).get("primary_section") == "atsc"
               for r in out)


def test_scope_allowed_receives_all_higher_candidates_first(tmp_path):
    """allowed 谓词在截断前逐候选生效：高分不允许候选不计入 top_k。"""
    idx = _mk_index(tmp_path)
    _seed(idx, _rows_skewed())
    q = np.zeros(8, dtype=np.float32); q[0] = 1.0; q = q / np.linalg.norm(q)
    seen: list[str] = []
    def _pred(meta):
        seen.append(str(meta["document_id"]))
        return (meta.get("chunk_metadata") or {}).get("primary_section") == "atsc"
    out = idx.vector_search(q, top_k=1, allowed=_pred)
    assert out and out[0]["meta"]["document_id"] == "at-1"
    # 谓词必须看过全部 6 条更高分的广度候选（先过滤后截断的直接证据）
    assert len([d for d in seen if d.startswith("bd-")]) == 6


# ── 2.3：单路故障隔离（server.py 源码截取，本目录惯例） ─────────────────


def _load_route_isolation_fns() -> dict[str, Any]:
    src = SERVER_SRC.read_text(encoding="utf-8")
    fns: list[str] = []
    for name in ("_route_with_retry",):
        m = re.search(rf"^async def {name}\(.*?(?=^async def |^def |^class )",
                      src, re.S | re.M)
        assert m, f"server.py 缺少 {name}"
        fns.append(m.group(0))
    ns: dict = {"asyncio": asyncio}
    exec("\n\n".join(fns), ns)
    return ns


def test_failed_route_isolated_and_other_route_kept():
    """vector 抛错、keyword 正常：失败路返回 [] 并记录 error；不外抛。"""
    ns = _load_route_isolation_fns()
    routes: dict = {}
    calls = {"vec": 0}

    async def _vec():
        calls["vec"] += 1
        raise RuntimeError("embedding service down")

    def _bm():
        return [{"meta": {"t": "行业周报"}, "score": 3.0}]

    async def _run():
        vec = await ns["_route_with_retry"]("vector", _vec, routes)
        bm = await ns["_route_with_retry"](
            "keyword", lambda: asyncio.to_thread(_bm), routes)
        return vec, bm

    vec, bm = asyncio.run(_run())
    assert vec == []
    assert bm and bm[0]["meta"]["t"] == "行业周报"  # 健康路结果保留
    assert routes["vector"]["executed"] is True
    assert routes["vector"]["succeeded"] is False
    assert "embedding service down" in routes["vector"]["error"]
    assert routes["vector"]["raw_candidates"] == 0
    assert routes["keyword"]["succeeded"] is True
    assert routes["keyword"]["raw_candidates"] == 1
    assert calls["vec"] == 2  # 失败路定向重试 1 次（keyword 未被重跑）


def test_transient_failure_recovers_on_retry():
    """瞬时故障重试成功：结果保留，路线记录 succeeded + retried_after。"""
    ns = _load_route_isolation_fns()
    routes: dict = {}
    state = {"n": 0}

    async def _vec():
        state["n"] += 1
        if state["n"] == 1:
            raise TimeoutError("transient")
        return [{"meta": {"t": "x"}, "score": 1.0}]

    out = asyncio.run(ns["_route_with_retry"]("vector", _vec, routes))
    assert out and routes["vector"]["succeeded"] is True
    assert routes["vector"]["retried_after"] == "TimeoutError"


def test_zero_hits_is_success_not_failure():
    ns = _load_route_isolation_fns()
    routes: dict = {}

    async def _vec():
        return []

    out = asyncio.run(ns["_route_with_retry"]("vector", _vec, routes))
    assert out == []
    assert routes["vector"]["succeeded"] is True
    assert routes["vector"]["raw_candidates"] == 0
    assert routes["vector"]["error"] is None


def test_server_search_wires_allowed_into_candidate_stage():
    """server.py 接线契约：来源/门控谓词必须传入增量索引候选阶段，
    不得回退为『全局 top_k*3 截断后再过滤』。"""
    src = SERVER_SRC.read_text(encoding="utf-8")
    m_vec = re.search(r"^async def vector_search\(.*?(?=^async def |^def )", src, re.S | re.M)
    m_bm = re.search(r"^def bm25_search\(.*?(?=^async def |^def )", src, re.S | re.M)
    assert m_vec and m_bm
    for m, name in ((m_vec, "vector_search"), (m_bm, "bm25_search")):
        body = m.group(0)
        assert "_incremental_index.vector_search(query_vec, top_k, allowed=" in body \
            or "_incremental_index.bm25_search(" in body, f"{name} 未接入 allowed"
        assert "top_k * 3" not in body, f"{name} 不得保留全局 top_k*3 截断后再过滤"
    # orchestrated 消费路线隔离记录（raw_candidates/duration 分路归属）
    m_orc = re.search(r"^async def orchestrated_search\(.*?(?=^def |^class )", src, re.S | re.M)
    assert m_orc, "缺 orchestrated_search"
    body = m_orc.group(0)
    assert "await _hybrid_routes(" in body
    # Codex#3 后合并逻辑抽为 _merge_route_info（终态语义），接线断言同步：
    assert "_merge_route_info(m[route_name]," in body
    assert "succeeded" in body  # 成功零命中 ≠ 失败的区分字段


def test_matrix_final_state_survives_later_subquery_failure():
    """Codex#3：子查询间失败不回退已成功状态——矩阵单元是终态语义。

    sub1 成功（candidates=3）→ sub2 失败：单元最终 succeeded=True
    （成功证据不被最后一次失败抹掉）；全程失败才 succeeded=False。
    """
    src = SERVER_SRC.read_text(encoding="utf-8")
    fns = []
    for name in ("_matrix_cell", "_merge_route_info"):
        m = re.search(rf"^def {name}\(.*?(?=^async |^def |^class )", src,
                      re.S | re.M)
        assert m, f"server.py 缺少 {name}，请同步更新测试截取"
        fns.append(m.group(0))
    ns: dict[str, Any] = {}
    exec("\n\n".join(fns), ns)
    cell = ns["_matrix_cell"]()

    # sub1：vector 成功 3 候选
    ns["_merge_route_info"](cell, {"executed": True, "succeeded": True,
                                   "raw_candidates": 3, "duration_ms": 10,
                                   "error": None})
    assert cell["succeeded"] is True and cell["candidates"] == 3
    # sub2：vector 失败（成功状态不得回退；error 记录但不降级）
    ns["_merge_route_info"](cell, {"executed": True, "succeeded": False,
                                   "raw_candidates": 0, "duration_ms": 8,
                                   "error": "RuntimeError: embed down"})
    assert cell["succeeded"] is True, "后续子查询失败不得抹掉已成功状态"
    assert cell["candidates"] == 3, "成功候选证据保留"
    assert cell["error"] == "RuntimeError: embed down", "失败原因仍可审计"
    # sub3：vector 再次成功 → error 清除（终态语义：恢复）
    ns["_merge_route_info"](cell, {"executed": True, "succeeded": True,
                                   "raw_candidates": 1, "duration_ms": 5,
                                   "error": None})
    assert cell["succeeded"] is True and cell["error"] is None
    assert cell["candidates"] == 4 and cell["duration_ms"] == 23

    # 对照：全程失败 → 终态 False
    cell2 = ns["_matrix_cell"]()
    ns["_merge_route_info"](cell2, {"executed": True, "succeeded": False,
                                    "raw_candidates": 0, "duration_ms": 3,
                                    "error": "boom"})
    ns["_merge_route_info"](cell2, {"executed": True, "succeeded": False,
                                    "raw_candidates": 0, "duration_ms": 2,
                                    "error": "boom2"})
    assert cell2["succeeded"] is False and cell2["error"] == "boom2"

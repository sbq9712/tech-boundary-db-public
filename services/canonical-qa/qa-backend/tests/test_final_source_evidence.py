"""Run production orchestration functions with isolated deterministic route inputs."""
import ast
import asyncio
from pathlib import Path
import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retrieval_pipeline as pipeline


def row(scope, i=0, relevant=True):
    text = "固态电解质界面阻抗内部评估能量密度350Wh/kg" if relevant else "海洋洋流观测"
    return {"meta": {"kind": "upload", "document_id": f"{scope}-{i}", "chunk_id": "0",
                     "chunk_metadata": {"primary_section": scope}, "t": text, "b": text},
            "title": text, "body_snippet": text, "score": .1}


def scope(meta):
    return meta["chunk_metadata"]["primary_section"]


def test_relevant_small_source_survives_global_cut_without_reserving_irrelevant():
    rows = [row("breadth", i) for i in range(60)] + [row("atsc"), row("industry", relevant=False)]
    out, trace = pipeline.select_source_evidence(rows, "固态电解质界面阻抗内部评估能量密度", 25, scope)
    assert len(out) == 25
    assert "atsc-0" in [r["meta"]["document_id"] for r in out]
    assert "industry" not in trace["reserved_relevant"]
    assert "industry-0" not in [r["meta"]["document_id"] for r in out]
    assert pipeline.select_source_evidence(rows, "", 0, scope)[0] == []


def runtime(failure=None):
    source = Path(__file__).resolve().parents[1] / "server.py"
    names = {"_route_with_retry", "_hybrid_routes", "_bm25_by_label", "_matrix_cell",
             "_merge_route_info", "orchestrated_search", "_pl_result_key"}
    nodes = [n for n in ast.parse(source.read_text()).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    ns = {"asyncio": asyncio, "FINAL_TOP_K": 25, "RETRIEVAL_TOP_K": 50,
          "RELEVANCE_FLOOR": .2, "VALID_SOURCES": ("breadth", "industry", "atsc"),
          "UNATTRIBUTED_SCOPE": "unattributed", "_STATIC_GRAPH_STATE": {},
          "FLAGS": {"SEMANTIC_GRAPH_ENABLED": True, "ENTITY_RESOLUTION_ENABLED": True,
                    "RERANKER_ENABLED": True, "EVIDENCE_GRADER_ENABLED": True},
          "_meta_scope": lambda meta, **kw: scope(meta),
          "_pl_decompose": lambda q, f: ([q], {}),
          "_pl_rrf_merge": pipeline.rrf_merge_rounds, "_pl_rerank": pipeline.rerank_results,
          "_pl_grade": pipeline.grade_evidence, "_pl_match_entities": pipeline.match_entities,
          "_pl_graph_expand": pipeline.graph_expand,
          "dedup_search_results": lambda results: (results, 0),
          "_hydrate_texts": lambda results: results,
          "rrf_fuse": lambda v, k: v or k}
    async def vector(q, top_k, sources):
        if failure == "vector" and sources == ("atsc",):
            raise RuntimeError("vector failure")
        return [] if sources == ("unattributed",) else [row(sources[0])]
    def keyword(q, top_k, sources):
        if failure == "keyword" and sources == ("atsc",):
            raise RuntimeError("keyword failure")
        if failure == "graph_label" and q == "电解质" and sources == ("atsc",):
            raise RuntimeError("graph label failure")
        return [] if sources == ("unattributed",) else [row(sources[0])]
    def graph(sc):
        return ([(sc, "固态", 1)], {sc: [("电解质", "研究")]})
    ns.update(vector_search=vector, bm25_search=keyword, _merged_graph=graph)
    if failure == "graph_expand":
        def fail(*args):
            raise RuntimeError("traversal failure")
        ns["_pl_graph_expand"] = fail
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns


def test_nine_cells_have_actual_candidate_and_selected_ids_and_graph_paths():
    ns = runtime()
    out, ev, trace = asyncio.run(ns["orchestrated_search"]("固态电解质界面阻抗"))
    for sc in ("breadth", "industry", "atsc"):
        key = pipeline.evidence_id(row(sc))
        for route in ("vector", "keyword", "graph"):
            cell = trace["source_route_matrix"][sc][route]
            assert cell["succeeded"] is True
            assert key in cell["candidate_ids"] and key in cell["selected_ids"]
        assert trace["source_route_matrix"][sc]["graph"]["candidate_paths"][key]
    assert all(set(r["meta"]["retrieval_routes"]) == {"vector", "keyword", "graph"} for r in out)


@pytest.mark.parametrize("failure,route", [("vector", "vector"), ("keyword", "keyword"),
    ("graph_label", "graph"), ("graph_expand", "graph")])
def test_fault_inside_route_preserves_healthy_source_evidence(failure, route):
    ns = runtime(failure)
    out, ev, trace = asyncio.run(ns["orchestrated_search"]("固态电解质界面阻抗"))
    assert {scope(r["meta"]) for r in out} == {"breadth", "industry", "atsc"}
    assert not trace.get("degraded")
    assert trace["source_route_matrix"]["atsc"][route]["succeeded"] is False
    assert trace["source_route_matrix"]["industry"]["vector"]["succeeded"] is True

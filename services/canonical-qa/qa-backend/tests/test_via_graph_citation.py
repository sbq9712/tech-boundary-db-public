"""任务二 2.3 可观测性：图谱扩展召回的 via_graph 归因必须在引用层透传。

背景（2026-10-02 验收演练发现）：orchestrated_search 图谱扩展在
result.meta 注入 via_graph=<桥接实体>，但 build_context 重建 citation
时丢弃了该字段——/api/search 与门户问答的引用里图谱路的真实贡献
不可见，「图谱非装饰路线」无法从外部验证。修复：citation 顶层透传
via_graph（非图谱路记录为 None，保持向后兼容）。

不导入完整 server.py（顶层依赖 FastAPI/numpy），从源码截取
build_context 纯函数执行（与 test_hydrate_upload_texts 同约定）。

截取用 ast 定位函数边界（Codex r4 P3-2：正则锚点对源码改动脆弱——
装饰器/注释/空行变化都会错位；ast 按节点行号精确切分）。
"""
import ast
import json
import tempfile
from pathlib import Path

import pytest

SERVER_SRC = Path(__file__).resolve().parent.parent / "server.py"


def _extract_func_src(src: str, *names: str) -> str:
    """按 ast 节点行号精确截取顶层函数源码（含装饰器），未命中即断言失败。"""
    tree = ast.parse(src)
    found: dict[str, ast.FunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            found[node.name] = node
    missing = [n for n in names if n not in found]
    assert not missing, f"server.py 缺少函数: {missing}（结构变化，请更新测试截取）"
    lines = src.splitlines(keepends=True)
    out = []
    for n in names:
        node = found[n]
        start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
        out.append("".join(lines[start:node.end_lineno]))
    return "\n".join(out)


def _load_build_context(lite_records: list):
    src = SERVER_SRC.read_text(encoding="utf-8")
    func_src = _extract_func_src(src, "load_records", "build_context")
    tmp = Path(tempfile.mkdtemp())
    lite = tmp / "lite.json"
    lite.write_text(json.dumps(lite_records), encoding="utf-8")
    ns = {"LITE_PATH": lite, "json": json, "_records": None}
    exec(func_src, ns)
    return ns["build_context"]


def _meta(**kw):
    base = {"kind": "upload", "document_id": "d1", "chunk_id": "d1-0",
            "t": "图谱桥接记录", "d": "2026-09-20", "u": "https://t/1",
            "chunk_metadata": {"primary_section": "breadth"}}
    base.update(kw)
    return base


def test_via_graph_passthrough_to_citation():
    build_context = _load_build_context([])
    results = [
        {"meta": dict(_meta(document_id="d1"), via_graph="催化材料"), "score": 0.9},
        {"meta": _meta(document_id="d2", t="普通向量召回"), "score": 0.8},
    ]
    _ctx, citations = build_context(results)
    assert citations[0]["via_graph"] == "催化材料", "图谱扩展召回的桥接实体必须在引用层可见"
    assert citations[1]["via_graph"] is None, "非图谱路记录 via_graph=None（向后兼容）"


def test_via_graph_absent_key_still_safe():
    """meta 不含 via_graph 键（历史调用方）不报错。"""
    build_context = _load_build_context([])
    results = [{"meta": _meta(document_id="d3", t="无桥接字段"), "score": 0.7}]
    _ctx, citations = build_context(results)
    assert citations[0]["via_graph"] is None

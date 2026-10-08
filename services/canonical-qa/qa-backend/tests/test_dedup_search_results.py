"""dedup_search_results 单元测试。

不导入完整 server.py（其顶层依赖 FastAPI/numpy 等运行时依赖），
而是从源码截取 dedup_search_results + load_records 两个纯函数，
对三类身份键（record_id/url/title|date|source）与 upload 文档折叠做验证。
语义与 tech-db 原版一致：keep-first，调用方（rrf_fuse 输出）按分数降序，
因此 first 即最高分。
"""
import ast
import json
import re
import tempfile
from pathlib import Path

import pytest

SERVER_SRC = Path(__file__).resolve().parent.parent / "server.py"


def _load_fn(lite_records: list):
    src = SERVER_SRC.read_text(encoding="utf-8")
    m1 = re.search(r"\ndef load_records\(\).*?(?=\ndef )", src, re.S)
    m2 = re.search(
        r"\ndef dedup_search_results\(.*?(?=\n(?:def |@|# ──|async def))", src, re.S)
    assert m1 and m2, "server.py 结构变化，请更新测试截取"
    tmp = Path(tempfile.mkdtemp())
    lite = tmp / "lite.json"
    lite.write_text(json.dumps(lite_records), encoding="utf-8")
    ns = {"LITE_PATH": lite, "json": json, "_records": None}
    ns.update(VALID_SOURCES=("breadth", "industry", "atsc"), UNATTRIBUTED_SCOPE="unattributed")
    scope = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_meta_scope")
    exec(compile(ast.Module(body=[scope], type_ignores=[]), str(SERVER_SRC), "exec"), ns)
    exec(m1.group(0) + m2.group(0), ns)
    return ns["dedup_search_results"]


LITE = [
    {"t": "固态电池突破", "d": "2026-09-01", "a": "来源A", "u": "https://x/1"},
    {"t": "固态电池突破", "d": "2026-09-01", "a": "来源A", "u": "https://x/1"},
    {"t": "氢能进展", "d": "2026-09-02", "a": "来源B", "u": "https://x/2"},
]


@pytest.fixture()
def dedup():
    return _load_fn(LITE)


def r(idx, score=1.0, **meta):
    m = {"idx": idx}
    m.update(meta)
    return {"meta": m, "score": score}


def test_collapses_same_article_keeps_first(dedup):
    res, dropped = dedup([r(1, 0.5), r(0, 0.9), r(2, 0.7)])
    assert dropped == 1 and len(res) == 2
    assert res[0]["meta"]["idx"] == 1  # keep-first（上游按分数降序）


def test_uploads_collapse_by_document(dedup):
    res, dropped = dedup([
        r(0, 0.9, kind="upload", document_id="d1"),
        r(1, 0.6, kind="upload", document_id="d1"),
        r(2, 0.7, kind="upload", document_id="d2"),
    ])
    assert dropped == 1 and len(res) == 2
    assert res[0]["meta"]["document_id"] == "d1"


def test_url_key(dedup):
    res, dropped = dedup([r(0, 0.9), r(1, 0.8)])
    assert dropped == 1 and res[0]["meta"]["idx"] == 0


def test_distinct_articles_kept(dedup):
    res, dropped = dedup([r(0), r(2)])
    assert dropped == 0 and len(res) == 2


def test_empty_input(dedup):
    assert dedup([]) == ([], 0)


def test_independent_sources_with_same_title_url_survive(dedup):
    items = [r(i, kind="upload", document_id=f"doc-{scope}", t="同名", d="2026-10-08",
               u="https://same/report", chunk_metadata={"primary_section": scope})
             for i, scope in enumerate(("breadth", "industry", "atsc"))]
    result, dropped = dedup(items)
    assert dropped == 0 and len(result) == 3

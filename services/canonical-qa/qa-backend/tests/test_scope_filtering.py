"""任务二 2.2：来源范围（sources）过滤单元测试。

不导入完整 server.py（顶层依赖 FastAPI/numpy 运行时），按本目录惯例
从源码截取 parse_sources / _meta_scope / _scope_allowed 三个纯函数验证：

- parse_sources：空/全非法 → None（默认全源）；合法子集去空格小写化；
- _meta_scope：基线= breadth；增量按 chunk_metadata.primary_section，
  非法/缺失 → unattributed；
- _scope_allowed：sources=None 全放行；收窄时未归属仅当显式包含
  "unattributed" 才放行（默认三源模式不静默丢证据的边界对称）。
"""

import re
from pathlib import Path

SERVER_SRC = Path(__file__).resolve().parent.parent / "server.py"


def _load_scope_fns():
    src = SERVER_SRC.read_text(encoding="utf-8")
    # 只截取两行常量定义（中间夹的注释行原样保留，避免吞入后续类定义）
    m_const = re.search(
        r'^VALID_SOURCES = \([^)]*\)\n(?:(?!^def |^class ).*\n)*?^UNATTRIBUTED_SCOPE = "unattributed"$',
        src, re.M)
    fns = []
    for name in ("parse_sources", "_meta_scope", "_scope_allowed"):
        m = re.search(
            rf"^def {name}\(.*?(?=^\ndef |^async def |^class |^_SHA_POSITIONS)",
            src, re.S | re.M)
        assert m, f"server.py 缺少 {name}，请同步更新测试截取"
        fns.append(m.group(0))
    assert m_const, "server.py 缺少 VALID_SOURCES/UNATTRIBUTED_SCOPE 常量"
    ns: dict = {}
    exec(m_const.group(0) + "\n\n" + "\n\n".join(fns), ns)
    return ns


NS = _load_scope_fns()
parse_sources = NS["parse_sources"]
_meta_scope = NS["_meta_scope"]
_scope_allowed = NS["_scope_allowed"]


# ── parse_sources ──

def test_parse_sources_empty_is_none():
    assert parse_sources(None) is None
    assert parse_sources("") is None
    assert parse_sources("   ") is None
    assert parse_sources(",") is None


def test_parse_sources_invalid_falls_back_to_none():
    # 全部非法值 → None = 默认全源（不抛错，保持旧 QA 行为）
    assert parse_sources("foo,bar") is None
    assert parse_sources("新闻") is None


def test_parse_sources_valid_subset_normalized():
    assert parse_sources("breadth") == ("breadth",)
    assert parse_sources(" Breadth , ATSC ") == ("breadth", "atsc")
    assert parse_sources("breadth,breadth,industry") == ("breadth", "breadth", "industry")
    # 未归属是可显式选择的诊断值，但不是默认三源之一
    assert parse_sources("unattributed") is None


# ── _meta_scope ──

def test_meta_scope_base_is_breadth():
    assert _meta_scope({"anything": 1}, is_base=True) == "breadth"


def test_meta_scope_incremental_by_primary_section():
    md = {"chunk_metadata": {"primary_section": "industry"}}
    assert _meta_scope(md, is_base=False) == "industry"
    assert _meta_scope({"chunk_metadata": {}}, is_base=False) == "unattributed"
    assert _meta_scope({"chunk_metadata": {"primary_section": "新闻"}}, is_base=False) == "unattributed"
    assert _meta_scope({}, is_base=False) == "unattributed"


# ── _scope_allowed ──

def test_scope_allowed_none_sources_allows_everything():
    for is_base in (True, False):
        for md in ({"chunk_metadata": {"primary_section": "atsc"}}, {}, {"chunk_metadata": {}}):
            assert _scope_allowed(md, is_base=is_base, sources=None) is True


def test_scope_allowed_scoped_matching():
    md = {"chunk_metadata": {"primary_section": "atsc"}}
    assert _scope_allowed(md, is_base=False, sources=("atsc",)) is True
    assert _scope_allowed(md, is_base=False, sources=("breadth",)) is False
    # 基线记录永远 breadth
    assert _scope_allowed({}, is_base=True, sources=("breadth",)) is True
    assert _scope_allowed({}, is_base=True, sources=("atsc",)) is False


def test_scope_allowed_unattributed_only_when_explicit():
    md = {"chunk_metadata": {}}
    # 三源收窄不含 unattributed → 排除
    assert _scope_allowed(md, is_base=False, sources=VALID_SOURCES) is False
    # 显式包含才放行（诊断场景）
    assert _scope_allowed(md, is_base=False, sources=("unattributed",)) is True


VALID_SOURCES = NS["VALID_SOURCES"]

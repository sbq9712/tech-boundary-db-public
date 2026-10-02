"""_hydrate_texts 上传分支单元测试（T12 演练回归）。

不导入完整 server.py（顶层依赖 FastAPI/numpy），从源码截取
_hydrate_texts + load_records 纯函数执行。

背景（2026-10-02 T12 生产演练发现）：feed 导入/管线同步的记录型
chunk meta 只有统一记录形字段（t/d/c/as/b/tg），没有
filename/title/chunk_text——旧实现 hydrate 出空标题/空正文，
rerank 词覆盖恒 0，增量导入的新记录在 QA 检索里永远沉底，
等于永远召不回。修复后 t/d/c/as/b/tg 兜底生效。
"""
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
        r"\ndef _hydrate_texts\(.*?(?=\n(?:async def |def |# ──))", src, re.S)
    assert m1 and m2, "server.py 结构变化，请更新测试截取"
    tmp = Path(tempfile.mkdtemp())
    lite = tmp / "lite.json"
    lite.write_text(json.dumps(lite_records), encoding="utf-8")
    ns = {"LITE_PATH": lite, "json": json, "_records": None}
    exec(m1.group(0) + m2.group(0), ns)
    return ns["_hydrate_texts"]


def _meta(**kw):
    base = {"kind": "upload", "document_id": "d1", "chunk_id": "d1-0"}
    base.update(kw)
    return base


# ── 记录型 chunk（feed 导入 / 管线同步）────────────────────────────


def test_record_chunk_hydrates_title_date_category_body():
    fn = _load_fn([])
    meta = _meta(
        t="【T12演练】'Crawzilla'——科学家发现北美已知最大的螯虾",
        d="2026-09-30",
        c="科技动态",
        **{"as": "北美发现巨型螯虾"},
        b="科学家在北美发现已知最大的螯虾物种 Crawzilla……",
        tg=["生物"],
        filename="",
    )
    out = fn([{"meta": meta, "score": 0.9}])[0]
    assert out["title"] == meta["t"]
    assert out["date"] == "2026-09-30"
    assert out["category"] == "科技动态"
    # 正文来自 as + b + tags（与基线记录同一公式）
    assert "Crawzilla" in out["body_snippet"]
    assert "北美发现巨型螯虾" in out["body_snippet"]  # as 前置
    assert "生物" in out["body_snippet"]  # tags 尾接


def test_record_chunk_without_filename_uses_t():
    fn = _load_fn([])
    meta = _meta(t="增量导入标题", d="2026-10-01", c="产业")
    out = fn([{"meta": meta, "score": 0.5}])[0]
    assert out["title"] == "增量导入标题"
    assert out["date"] == "2026-10-01"


def test_body_snippet_truncated_to_600():
    fn = _load_fn([])
    meta = _meta(t="长文", b="x" * 5000)
    out = fn([{"meta": meta, "score": 0.5}])[0]
    assert len(out["body_snippet"]) == 600


def test_tags_string_normalized():
    fn = _load_fn([])
    meta = _meta(t="带标签", b="正文", tg="单标签")
    out = fn([{"meta": meta, "score": 0.5}])[0]
    assert "单标签" in out["body_snippet"]


# ── 手动上传 chunk（保持旧行为）──────────────────────────────────


def test_manual_upload_filename_priority_kept():
    fn = _load_fn([])
    meta = _meta(filename="report.pdf", t="报告标题", b="正文内容")
    out = fn([{"meta": meta, "score": 0.5}])[0]
    # 手动上传：filename 优先（与旧实现一致）
    assert out["title"] == "report.pdf"
    assert "正文内容" in out["body_snippet"]


def test_manual_upload_default_category_when_no_c():
    fn = _load_fn([])
    meta = _meta(t="无分类上传")
    out = fn([{"meta": meta, "score": 0.5}])[0]
    assert out["category"] == "上传资料"
    assert out["date"] == ""


def test_legacy_chunk_text_still_wins():
    fn = _load_fn([])
    meta = _meta(t="新字段标题", b="新字段正文", chunk_text="旧通道正文")
    out = fn([{"meta": meta, "score": 0.5}])[0]
    # 显式 chunk_text 存在时优先（兼容旧写入路径）
    assert out["body_snippet"] == "旧通道正文"


# ── 基线记录分支（回归：不走 upload 字段）──────────────────────


def test_base_record_unchanged_by_upload_fix():
    lite = [{"t": "基线标题", "d": "2026-01-01", "c": "基线类",
             "as": "摘要", "b": "正文", "tg": ["tag1"], "idx": 0}]
    fn = _load_fn(lite)
    out = fn([{"meta": {"idx": 0}, "score": 0.1}])[0]
    assert out["title"] == "基线标题"
    assert out["category"] == "基线类"
    assert out["date"] == "2026-01-01"
    assert "摘要" in out["body_snippet"] and "tag1" in out["body_snippet"]


# ── 端到端语义：hydrate 后 rerank 词覆盖不再恒 0 ─────────────────


def test_hydrated_upload_has_term_coverage_for_rerank():
    """模拟 rerank_results 的词覆盖计算：修复前 upload 类覆盖恒 0。"""
    fn = _load_fn([])
    meta = _meta(
        t="【T12演练】Luma CEO Amit Jain：世界模型需要更多智能",
        d="2026-09-22", c="科技动态", b="Luma AI CEO 谈世界模型与更多智能",
    )
    out = fn([{"meta": meta, "score": 0.5}])[0]
    query_terms = ["luma", "世界模型", "智能"]
    title = out["title"].lower()
    body = out["body_snippet"].lower()
    covered = sum(1 for t in query_terms if t.lower() in title or t.lower() in body)
    assert covered == len(query_terms), "hydrate 后查询词应全部可命中"

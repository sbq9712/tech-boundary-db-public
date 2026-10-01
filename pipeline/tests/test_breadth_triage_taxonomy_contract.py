"""Breadth UI must expose triage_engine's display taxonomy, not legacy 5+2 tags."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "breadth" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "breadth" / "index.html").read_text(encoding="utf-8")

NEWS = (
    "知识资产",
    "工程与产业化",
    "企业经营、合作与资本",
    "资源、市场与产业链",
    "政策、法规与标准",
    "人才与组织动态",
    "观点与交流",
)
LITERATURE = ("综述", "研究型", "分析类", "新闻/评论/观点")


def test_current_triage_taxonomy_is_frontend_source_order():
    for tag in NEWS + LITERATURE:
        assert tag in APP
    assert "TRIAGE_TYPE_TAGS" in APP
    assert "renderTypePopovers" in APP


def test_legacy_popovers_are_not_hardcoded_in_html():
    assert 'id="popover-news"' in INDEX
    assert 'id="popover-literature"' in INDEX
    assert 'data-tag="技术突破"' not in INDEX
    assert 'data-tag="研究论文"' not in INDEX


def test_legacy_values_are_explicit_transition_only():
    assert "LEGACY_TYPE_TAGS" in APP
    assert "旧数据" in APP

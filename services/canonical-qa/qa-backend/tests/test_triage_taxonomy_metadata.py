"""Current triage_engine tags must retain useful QA evidence metadata."""
from epistemic import infer_source_type
from evidence_metadata import infer_evidence_role


def test_literature_subtypes_are_academic():
    for tag in ("综述", "研究型", "分析类", "新闻/评论/观点"):
        assert infer_source_type({"tg": tag, "a": "Journal"}) == "academic_paper"


def test_policy_and_news_display_classes_are_understood():
    assert infer_source_type({"tg": "政策、法规与标准", "a": "某主管部门"}) == "government"
    assert infer_source_type({"tg": "工程与产业化", "a": "某公司"}) == "company_announcement"
    assert infer_source_type({"tg": "资源、市场与产业链", "a": "行业研究"}) == "industry_report"


def test_evidence_roles_support_current_and_legacy_tags():
    assert infer_evidence_role({"tg": "工程与产业化", "a": "某公司"}) == "self_reported"
    assert infer_evidence_role({"tg": "观点与交流", "a": "行业媒体"}) == "commentary"
    assert infer_evidence_role({"tg": "观点评论", "a": "行业媒体"}) == "commentary"

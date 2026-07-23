from types import SimpleNamespace

from app.routers.dashboards import _is_boundary_parameter, _parameter_payload


def _param(name: str, parameter_type: str):
    return SimpleNamespace(parameter_name=name, parameter_type=parameter_type)


def test_boundary_parameter_keeps_technical_and_decision_causal_economics():
    assert _is_boundary_parameter(_param("系统电耗", "technical"))
    assert _is_boundary_parameter(_param("绿电价格", "economic"))
    assert _is_boundary_parameter(_param("电解槽CAPEX", "economic"))
    assert _is_boundary_parameter(_param("绿氨LCOA", "economic"))


def test_boundary_parameter_rejects_industry_scale_proxies():
    assert not _is_boundary_parameter(_param("全球市场规模", "economic"))
    assert not _is_boundary_parameter(_param("企业订单总量", "commercial"))
    assert not _is_boundary_parameter(_param("可用产能", "economic"))
    assert not _is_boundary_parameter(_param("年度融资额", "economic"))


def test_parameter_payload_keeps_commercial_status_separate_from_verification():
    param = SimpleNamespace(
        parameter_name="AEM 寿命",
        parameter_type="technical",
        value_text="<10,000 小时",
        value_min=None,
        value_max=None,
        unit="",
        verification_status="human_checked",
    )

    payload = _parameter_payload(
        param,
        {"AEM 寿命": "below_commercial"},
        {"AEM 寿命": "低于工业寿命要求"},
    )

    assert payload["verification"] == "human_checked"
    assert payload["commercial_status"] == "below_commercial"
    assert payload["commercial_status_reason"] == "低于工业寿命要求"

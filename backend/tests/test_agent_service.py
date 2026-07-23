from app.services import agent_service
from types import SimpleNamespace

from app.services.agent_service import (
    _build_prompt,
    _build_retrieval_query,
    _match_dashboards,
    _parameter_value,
    _usable_indexed_parameters,
    _used_citations,
    resolve_model,
)


def test_prompt_keeps_all_prebounded_history_messages():
    history = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"message-{index}"}
        for index in range(30)
    ]
    messages = _build_prompt("current question", {}, history)
    assert len(messages) == 32  # system + 30 history messages + current question
    assert messages[1]["content"] == "message-0"
    assert messages[-2]["content"] == "message-29"
    assert "默认写成 3～6 个紧凑段落" in messages[0]["content"]
    assert "不要逐句分点" in messages[0]["content"]
    assert "Markdown 粗体（**...**）" in messages[0]["content"]


def test_used_citations_only_returns_refs_present_in_answer():
    candidates = [
        {"ref": "K1", "type": "knowledge_base"},
        {"ref": "S1", "type": "source"},
        {"ref": "P1", "type": "parameter"},
    ]
    assert _used_citations("事实来自 [S1]，参数来自 [P1]。", candidates) == candidates[1:]


def test_glm_5_1_is_an_allowed_model():
    assert resolve_model("glm-5.1") == "glm-5.1"


def test_build_prompt_caps_retrieval_context(monkeypatch):
    monkeypatch.setattr(agent_service, "AI_RETRIEVAL_MAX_CHARS", 120)
    retrieval = {
        "knowledge_base": [{
            "title": "large document",
            "path": "large.md",
            "score": 10,
            "context": "x" * 1000,
        }]
    }

    messages = _build_prompt("question", retrieval, [])

    assert "检索材料已按上下文预算截断" in messages[-1]["content"]
    assert len(messages[-1]["content"]) < 250


def test_referential_follow_up_reuses_previous_user_topic():
    history = [
        {"role": "user", "content": "液冷数据中心最关键的技术边界是什么？"},
        {"role": "assistant", "content": "需要验证散热和材料兼容性。"},
    ]

    rewritten = _build_retrieval_query("这些边界里优先验证哪两个？", history)

    assert "液冷数据中心" in rewritten
    assert rewritten.endswith("这些边界里优先验证哪两个？")
    assert _build_retrieval_query("请介绍固态电池", history) == "请介绍固态电池"


def test_generic_index_numbers_are_not_parameter_boundaries():
    rows = [
        {"parameter_name": "reported_number", "value": "2022"},
        {"parameter_name": "系统效率", "value": "60-65", "unit": "%"},
        {"parameter_name": "系统效率", "value": "60-65", "unit": "%"},
    ]

    result = _usable_indexed_parameters(rows)

    assert len(result) == 1
    assert result[0]["parameter_name"] == "系统效率"


def test_dashboard_match_does_not_pad_unrelated_items(monkeypatch):
    artifacts = [
        SimpleNamespace(
            artifact_type="deep_research_note",
            status="active",
            title="SOFC行业深度报告",
            vault_path="SOC/SOFC行业深度报告.md",
            stable_id="ART-20260712-4F444B2861",
            related_tech_node_ids=["tech_sofc"],
        ),
        SimpleNamespace(
            artifact_type="deep_research_note",
            status="active",
            title="钠电池_钠离子电池储能技术边界",
            vault_path="钠电池/钠电池_钠离子电池储能技术边界.md",
            stable_id="ART-20260709-NAION",
            related_tech_node_ids=["tech_na"],
        ),
    ]

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return artifacts

    class Db:
        def query(self, *_args):
            return Query()

    result = _match_dashboards(Db(), "SOFC数据中心电源", [{"path": "SOC/Bloom专利/技术摘要.md"}])

    assert [item["id"] for item in result] == ["4f444b2861"]


def test_dashboard_match_ignores_shared_generic_title_suffixes():
    artifacts = [
        SimpleNamespace(
            artifact_type="deep_research_note",
            status="active",
            title="SOFC行业深度报告",
            vault_path="SOC/SOFC行业深度报告.md",
            stable_id="ART-20260712-4F444B2861",
            related_tech_node_ids=["tech_sofc"],
        ),
        SimpleNamespace(
            artifact_type="deep_research_note",
            status="active",
            title="AIDC全产业链_供电与互连瓶颈_技术边界",
            vault_path="AIDC全产业链/AIDC全产业链_供电与互连瓶颈_技术边界.md",
            stable_id="ART-20260712-CB55BEB933",
            related_tech_node_ids=["tech_aidc"],
        ),
        SimpleNamespace(
            artifact_type="deep_research_note",
            status="active",
            title="AGENT_模拟世界学习_技术边界",
            vault_path="AGENT/AGENT_模拟世界学习_技术边界.md",
            stable_id="ART-20260712-FB270926D2",
            related_tech_node_ids=["tech_agent"],
        ),
    ]

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return artifacts

    class Db:
        def query(self, *_args):
            return Query()

    query = "SOFC\u5728\u6570\u636e\u4e2d\u5fc3\u5e94\u7528\u7684\u6280\u672f\u8fb9\u754c\u662f\u4ec0\u4e48\uff1f"
    kb_results = [
        {"path": "SOC/Bloom_Energy\u4e13\u5229/\u6280\u672f\u6458\u8981_\u4e2d\u6587.md"},
        {"path": "AGENT/AGENT_\u6a21\u62df\u4e16\u754c\u5b66\u4e60_\u6280\u672f\u8fb9\u754c.md"},
    ]

    result = _match_dashboards(Db(), query, kb_results)

    assert [item["id"] for item in result] == ["4f444b2861"]


def test_parameter_value_keeps_text_and_numeric_ranges():
    assert _parameter_value(SimpleNamespace(value_text="55%", value_min=None, value_max=None, unit="")) == "55%"
    assert _parameter_value(SimpleNamespace(value_text=None, value_min=40, value_max=60, unit="kWh/kg")) == "40-60 kWh/kg"

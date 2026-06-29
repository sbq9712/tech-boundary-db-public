from fastapi.testclient import TestClient

from app import readonly_agent
from app.readonly_agent import app


def test_readonly_agent_health(monkeypatch, tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "doc.md").write_text("# SOFC 文档\n电解质电导率", encoding="utf-8")
    monkeypatch.setattr(readonly_agent, "KNOWLEDGE_BASE_PATH", kb)
    with TestClient(app) as client:
        response = client.get("/health")
    payload = response.json()
    assert response.status_code == 200
    assert payload["agent"] == "techdb-readonly"
    assert payload["knowledge_base_mounted"] is True
    assert payload["markdown_files"] == 1


def test_readonly_agent_query_returns_contract(monkeypatch, tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "soc.md").write_text("# SOC 数据锚点\nSOFC 电解质电导率和堆寿命是关键参数。", encoding="utf-8")
    monkeypatch.setattr(readonly_agent, "KNOWLEDGE_BASE_PATH", kb)
    monkeypatch.setattr("app.readonly_agent._search_info_items", lambda _query: [])
    monkeypatch.setattr("app.readonly_agent._generate_ai_answer", lambda *_args: ("AI 生成回答", "medium", None))
    with TestClient(app) as client:
        response = client.post("/query", json={"query": "SOFC 电解质电导率"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["agent"] == "techdb-readonly"
    assert payload["confidence"] in {"high", "medium", "low"}
    assert isinstance(payload["verified_facts"], list)
    assert isinstance(payload["related_dashboards"], list)
    assert isinstance(payload["knowledge_documents"], list)
    assert payload["knowledge_documents"][0]["path"] == "soc.md"
    assert payload["answer"] == "AI 生成回答"
    assert "panel_recommendations" in payload
    assert set(payload["panel_recommendations"]) == {"hot_intel", "parameter_boundaries", "alert_intel", "dashboard_links"}
    assert isinstance(payload["panel_recommendations"]["dashboard_links"], list)

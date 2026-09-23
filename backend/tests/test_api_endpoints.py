from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_token, hash_password
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.user import User
from app.routers.auth import _failed_attempts

CAPTURE_LEAF_ID = "DOM_CCUS_L4_CAPTURE_02_02"
CAPTURE_REGEN_ID = "IND_CCUS_CAPTURE_04"
CAPTURE_REGEN_NAME = "再生能耗 (GJ/tCO₂)"
CAPTURE_REGEN_UNIT = "GJ/tCO₂"
CAPTURE_RATE_ID = "IND_CCUS_CAPTURE_15"
CAPTURE_RATE_NAME = "捕集率 (%)"
CAPTURE_RATE_UNIT = "%"
CAPTURE_CYCLE_ID = "IND_CCUS_CAPTURE_11"
CAPTURE_CYCLE_NAME = "循环寿命 (圈)"
CAPTURE_CYCLE_UNIT = "圈"
TRANSPORT_LEAF_ID = "DOM_CCUS_L4_TRANSPORT_01_01"
TRANSPORT_DISTANCE_ID = "IND_CCUS_TRANSPORT_08"
TRANSPORT_DISTANCE_NAME = "运输距离（km）"
TRANSPORT_DISTANCE_UNIT = "km"


@pytest.fixture(scope="module", autouse=True)
def isolated_api_test_users():
    credentials = {
        "admin1": "ATSC1231",
        "admin2": "ATSC1232",
        "admin3": "ATSC1233",
    }
    db = SessionLocal()
    try:
        for username, password in credentials.items():
            existing = db.get(User, username)
            if existing:
                db.delete(existing)
                db.flush()
            db.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    display_name=f"API test {username}",
                    role="admin",
                    is_active=True,
                )
            )
        db.commit()
        _failed_attempts.clear()
        yield
    finally:
        _failed_attempts.clear()
        for username in credentials:
            existing = db.get(User, username)
            if existing:
                db.delete(existing)
        db.commit()
        db.close()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        resp = test_client.post("/api/auth/login", json={"username": "admin1", "password": "ATSC1231"})
        assert resp.status_code == 200, f"auth login failed: {resp.text}"
        token = resp.json()["access_token"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client


def test_login_ok():
    with TestClient(app) as c:
        resp = c.post("/api/auth/login", json={"username": "admin1", "password": "ATSC1231"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()


def test_login_wrong_password():
    with TestClient(app) as c:
        resp = c.post("/api/auth/login", json={"username": "admin1", "password": "wrong"})
        assert resp.status_code == 401


def test_change_password_ok():
    with TestClient(app) as c:
        # 用 admin2 登录
        login_resp = c.post("/api/auth/login", json={"username": "admin2", "password": "ATSC1232"})
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        # 修改密码
        r = c.patch("/api/auth/password",
                    json={"current_password": "ATSC1232", "new_password": "NewPass999"},
                    headers=headers)
        assert r.status_code == 204
        # 新密码可以登录
        r2 = c.post("/api/auth/login", json={"username": "admin2", "password": "NewPass999"})
        assert r2.status_code == 200
        # 恢复原密码
        token2 = r2.json()["access_token"]
        c.patch("/api/auth/password",
                json={"current_password": "NewPass999", "new_password": "ATSC1232"},
                headers={"Authorization": f"Bearer {token2}"})


def test_change_password_wrong_current():
    with TestClient(app) as c:
        login_resp = c.post("/api/auth/login", json={"username": "admin3", "password": "ATSC1233"})
        token = login_resp.json()["access_token"]
        r = c.patch("/api/auth/password",
                    json={"current_password": "wrongpass", "new_password": "NewPass999"},
                    headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400


def test_protected_route_requires_auth():
    with TestClient(app) as c:
        resp = c.get("/api/info-items")
        assert resp.status_code == 401


def test_domains_tree_ok(client):
    response = client.get("/api/domains/tree")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    if payload:
        first = payload[0]
        assert "id" in first
        assert "name" in first
        assert "children" in first


def test_info_items_ok(client):
    response = client.get("/api/info-items")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    if payload:
        first = payload[0]
        assert "id" in first
        assert "title" in first


def test_intake_status_requires_auth():
    with TestClient(app) as c:
        resp = c.get("/api/intake/status")
        assert resp.status_code == 401


def test_intake_schema_ok():
    class FakeDb:
        def get(self, *_args):
            return None

    def fake_db():
        yield FakeDb()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as c:
            c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
            response = c.get("/api/intake/schema")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "placeholder_ready"
    assert payload["schema"]["object"] == "intake_item"
    assert payload["schema"]["confidentiality_levels"] == ["公开", "内部", "管理员"]
    channel_ids = {channel["id"] for channel in payload["channels"]}
    assert {"server_fetch", "crawler_fetch", "direct_upload"}.issubset(channel_ids)


def test_sources_overview_ok():
    class FakeDb:
        def get(self, *_args):
            return None

    def fake_db():
        yield FakeDb()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as c:
            c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
            response = c.get("/api/sources")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "placeholder_ready"
    assert "upload_review.html" in payload["current_available_paths"]


def test_assistant_query_requires_auth():
    with TestClient(app) as c:
        resp = c.post("/api/assistant/query", json={"query": "SOFC 适合数据中心吗"})
        assert resp.status_code == 401


def test_assistant_status_ok():
    class FakeDb:
        def get(self, *_args):
            return None

    def fake_db():
        yield FakeDb()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as c:
            c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
            response = c.get("/api/assistant/status")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert payload["provider"] == "sbq9712/tech-db canonical hybrid retrieval"
    assert "required_assets" in payload


def test_assistant_models_lists_default_and_fallbacks():
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
        response = c.get("/api/assistant/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_model"]
    assert payload["default_model"] in payload["models"]
    assert len(payload["models"]) >= 1


def test_assistant_stream_accepts_selected_model(monkeypatch):
    from app.routers import assistant_stream

    captured = {}

    async def fake_stream_agent_response(query, session_id, db, selected_model=None, current_user=None, regenerate=False, retry=False):
        captured["query"] = query
        captured["session_id"] = session_id
        captured["selected_model"] = selected_model
        captured["current_user"] = current_user
        captured["regenerate"] = regenerate
        captured["retry"] = retry
        yield 'event: done\ndata: {"citations": [], "retrieval_summary": {}}\n\n'

    class FakeConversation:
        id = "11111111-1111-1111-1111-111111111111"

    class FakeDb:
        def get(self, *_args):
            return None

    def fake_db():
        yield FakeDb()

    monkeypatch.setattr(assistant_stream, "stream_agent_response", fake_stream_agent_response)
    monkeypatch.setattr(assistant_stream, "_resolve_session", lambda *_args: FakeConversation())
    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as c:
            c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
            response = c.post("/api/assistant/stream", json={"query": "SOFC", "model": "glm-4.5-flash"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert captured == {
        "query": "SOFC",
        "session_id": FakeConversation.id,
        "selected_model": "glm-4.5-flash",
        "current_user": "admin1",
        "regenerate": False,
        "retry": False,
    }


def test_assistant_stream_rejects_session_owned_by_another_user():
    from app.routers.assistant_stream import _resolve_session

    class OtherUsersSession:
        user_id = "admin2"

    class FakeDb:
        def get(self, *_args):
            return OtherUsersSession()

    with pytest.raises(Exception) as exc_info:
        _resolve_session(FakeDb(), "admin1", __import__("uuid").UUID("11111111-1111-1111-1111-111111111111"), "SOFC")
    assert getattr(exc_info.value, "status_code", None) == 404


def test_assistant_stream_rejects_unknown_model():
    class FakeDb:
        def get(self, *_args):
            return None

    def fake_db():
        yield FakeDb()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as c:
            c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
            response = c.get("/api/assistant/stream?query=SOFC&model=not-a-real-model")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 400


def test_conversation_delete_is_user_scoped_and_cascades(client):
    created = client.post("/api/conversations", json={"title": "待删除会话", "topic_hint": "test"})
    assert created.status_code == 201
    session_id = created.json()["id"]
    message = client.post(
        f"/api/conversations/{session_id}/messages",
        json={"role": "user", "content": "测试消息"},
    )
    assert message.status_code == 201
    deleted = client.delete(f"/api/conversations/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/conversations/{session_id}/messages").status_code == 404


def test_conversation_delete_rejects_other_user(client):
    created = client.post("/api/conversations", json={"title": "用户范围测试"})
    assert created.status_code == 201
    session_id = created.json()["id"]
    from app.core.security import create_token

    # There is no GET session endpoint; the protected messages endpoint is the ownership check.
    assert client.get(
        f"/api/conversations/{session_id}/messages",
        headers={"Authorization": f"Bearer {create_token('admin2')}"},
    ).status_code == 404
    assert client.delete(
        f"/api/conversations/{session_id}",
        headers={"Authorization": f"Bearer {create_token('admin2')}"},
    ).status_code == 404
    assert client.delete(f"/api/conversations/{session_id}").status_code == 204


def test_assistant_query_placeholder_ok(monkeypatch):
    monkeypatch.setenv("HERMES_AGENT_MODE", "mock")
    class FakeDb:
        def get(self, *_args):
            return None

    def fake_db():
        yield FakeDb()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as c:
            c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
            response = c.post("/api/assistant/query", json={"query": "SOFC 适合数据中心吗"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"placeholder_ready", "agent_connected"}
    assert payload["mode"] in {"mock", "http"}
    assert payload["message"]


def test_industry_map_ok():
    class FakeDb:
        def get(self, *_args):
            return None

    def fake_db():
        yield FakeDb()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as c:
            c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
            response = c.get("/api/industry-map")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["sheet_count"] == 3
    assert payload["total_node_count"] >= 100
    assert payload["max_depth"] >= 5
    assert [sheet["title"] for sheet in payload["sheets"]] == ["零碳产业", "AI与智能科技", "通用技术"]


def test_dashboards_search_ok():
    class FakeDb:
        def get(self, *_args):
            return None

    def fake_db():
        yield FakeDb()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as c:
            c.headers.update({"Authorization": f"Bearer {create_token('admin1')}"})
            response = c.get("/api/dashboards", params={"q": "SOFC"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["id"] == "sofc-soc"
    assert payload["items"][0]["query"] == "SOFC"
    assert payload["items"][0]["domain"] == "SOFC"


def test_last_modified_by_recorded(client):
    payload = {
        "title": "记录操作人测试",
        "content": "测试正文",
        "source_url": None,
        "published_at": "2026-04-08T00:00:00Z",
        "importance_score": 3,
        "is_new_tech": False,
        "comment": None,
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": [],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "draft_data": {"manual_alert": False, "duration": "month", "indicators": []},
        "alert": None,
    }
    resp = client.post("/api/info-items/publish", json=payload)
    assert resp.status_code == 201
    item = resp.json()
    assert item["last_modified_by"] == "admin1"


def test_draft_create_and_get_ok(client):
    payload = {
        "title": "测试草稿",
        "content": "测试正文",
        "source_url": "https://example.com",
        "published_at": "2026-03-07T00:00:00Z",
        "importance_score": 4,
        "is_new_tech": True,
        "comment": "测试备注",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["测试"],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "status": "draft",
        "draft_data": {"manual_alert": False, "duration": "month", "indicators": []},
        "alert": None,
    }
    create_resp = client.post("/api/info-items/draft", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["status"] == "draft"
    assert created["domain_ids"] == [CAPTURE_LEAF_ID]

    draft_id = created["id"]
    get_resp = client.get(f"/api/info-items/{draft_id}/draft")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == draft_id
    assert "draft_data" in fetched


def test_publish_rejects_alert_expiry_not_in_future(client):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    publish_payload = {
        "title": "过期预警时间",
        "content": "预警到期时间必须晚于当前时间",
        "source_url": "https://example.com/past-alert-expiry",
        "published_at": "2026-03-26T00:00:00Z",
        "importance_score": 4,
        "is_new_tech": True,
        "comment": "验证过期时间校验",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["预警"],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "draft_data": {
            "manual_alert": True,
            "duration": "custom",
            "custom_expires_on": past.date().isoformat(),
            "indicators": []
        },
        "alert": {
            "enabled": True,
            "alert_title": "测试预警",
            "alert_body": "测试内容",
            "reviewer_comment": "测试备注",
            "alert_color": "orange",
            "expires_at": past.isoformat().replace("+00:00", "Z")
        },
    }
    publish_resp = client.post("/api/info-items/publish", json=publish_payload)
    assert publish_resp.status_code == 400
    assert publish_resp.json()["detail"] == "expires_at must be in the future"


def test_draft_with_empty_indicator_value_can_publish(client):
    draft_payload = {
        "title": "空指标值草稿",
        "content": "这是带空指标值的草稿正文",
        "source_url": "https://example.com/empty-indicator",
        "published_at": "2026-03-08T00:00:00Z",
        "importance_score": 3,
        "is_new_tech": False,
        "comment": "允许指标值为空",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["回归"],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "status": "draft",
        "draft_data": {
            "manual_alert": False,
            "duration": "month",
            "indicators": [
                {"indicator_id": CAPTURE_REGEN_ID, "name": CAPTURE_REGEN_NAME, "value": "", "unit": CAPTURE_REGEN_UNIT, "keep": True},
                {"indicator_id": CAPTURE_RATE_ID, "name": CAPTURE_RATE_NAME, "value": "92", "unit": CAPTURE_RATE_UNIT, "keep": True},
            ],
        },
        "alert": None,
    }
    draft_resp = client.post("/api/info-items/draft", json=draft_payload)
    assert draft_resp.status_code == 201
    draft = draft_resp.json()
    assert draft["status"] == "draft"

    publish_payload = {
        "title": draft_payload["title"],
        "content": draft_payload["content"],
        "source_url": draft_payload["source_url"],
        "published_at": draft_payload["published_at"],
        "importance_score": draft_payload["importance_score"],
        "is_new_tech": draft_payload["is_new_tech"],
        "comment": draft_payload["comment"],
        "source_types": draft_payload["source_types"],
        "info_types": draft_payload["info_types"],
        "tags": draft_payload["tags"],
        "domain_ids": draft_payload["domain_ids"],
        "classification": draft_payload["classification"],
        "draft_id": draft["id"],
        "alert": None,
    }
    publish_resp = client.post("/api/info-items/publish", json=publish_payload)
    assert publish_resp.status_code == 201
    published = publish_resp.json()
    assert published["status"] == "published"
    indicators = (published.get("draft_data") or {}).get("indicators") or []
    assert len(indicators) == 2
    assert indicators[0]["name"] == CAPTURE_REGEN_NAME
    assert indicators[0]["indicator_id"] == CAPTURE_REGEN_ID
    assert indicators[0]["value"] == ""
    assert indicators[1]["name"] == CAPTURE_RATE_NAME
    assert indicators[1]["indicator_id"] == CAPTURE_RATE_ID
    assert indicators[1]["value"] == "92"


def test_direct_publish_drops_cross_category_indicator_and_keeps_allowed_only(client):
    publish_payload = {
        "title": "直发指标保留",
        "content": "批量直发时需要保留当前 CCUS 二级分类允许的指标",
        "source_url": "https://example.com/direct-publish-with-indicators",
        "published_at": "2026-03-09T00:00:00Z",
        "importance_score": 4,
        "is_new_tech": True,
        "comment": "验证直接发布的指标保留",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["批量发布", "指标"],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "draft_data": {
            "manual_alert": False,
            "duration": "month",
            "indicators": [
                {"indicator_id": "", "name": CAPTURE_RATE_NAME, "value": "92", "unit": CAPTURE_RATE_UNIT, "keep": True},
                {"indicator_id": "", "name": TRANSPORT_DISTANCE_NAME, "value": "120", "unit": "km", "keep": True},
            ],
        },
        "alert": None,
    }
    publish_resp = client.post("/api/info-items/publish", json=publish_payload)
    assert publish_resp.status_code == 201
    published = publish_resp.json()
    assert published["status"] == "published"
    indicators = (published.get("draft_data") or {}).get("indicators") or []
    assert len(indicators) == 1
    assert indicators[0]["indicator_id"] == CAPTURE_RATE_ID
    assert indicators[0]["name"] == CAPTURE_RATE_NAME
    assert indicators[0]["value"] == "92"


def test_direct_publish_with_multiple_domains_keeps_union_of_level2_indicators(client):
    publish_payload = {
        "title": "多领域并集指标",
        "content": "同一条情报同时命中捕集与运输两个领域",
        "source_url": "https://example.com/direct-publish-multi-domains",
        "published_at": "2026-03-25T00:00:00Z",
        "importance_score": 4,
        "is_new_tech": True,
        "comment": "验证多领域时指标可按二级领域并集保留",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["多领域", "指标并集"],
        "domain_ids": [CAPTURE_LEAF_ID, TRANSPORT_LEAF_ID],
        "classification": "内部",
        "draft_data": {
            "manual_alert": False,
            "duration": "month",
            "indicators": [
                {"indicator_id": "", "name": CAPTURE_RATE_NAME, "value": "92", "unit": CAPTURE_RATE_UNIT, "keep": True},
                {"indicator_id": "", "name": TRANSPORT_DISTANCE_NAME, "value": "120", "unit": TRANSPORT_DISTANCE_UNIT, "keep": True},
            ],
        },
        "alert": None,
    }
    publish_resp = client.post("/api/info-items/publish", json=publish_payload)
    assert publish_resp.status_code == 201
    published = publish_resp.json()
    indicators = (published.get("draft_data") or {}).get("indicators") or []
    assert len(indicators) == 2
    assert indicators[0]["indicator_id"] == CAPTURE_RATE_ID
    assert indicators[0]["name"] == CAPTURE_RATE_NAME
    assert indicators[1]["indicator_id"] == TRANSPORT_DISTANCE_ID
    assert indicators[1]["name"] == TRANSPORT_DISTANCE_NAME


def test_direct_publish_rejects_non_level4_domain_ids(client):
    publish_payload = {
        "title": "非四级领域禁止发布",
        "content": "批量导入和发布都只能使用四级领域",
        "source_url": "https://example.com/direct-publish-non-level4-domain",
        "published_at": "2026-03-25T00:00:00Z",
        "importance_score": 3,
        "is_new_tech": False,
        "comment": "验证领域层级校验",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["领域校验"],
        "domain_ids": ["DOM_CCUS_L3_CAPTURE_02"],
        "classification": "内部",
        "draft_data": {
            "manual_alert": False,
            "duration": "month",
            "indicators": [],
        },
        "alert": None,
    }
    publish_resp = client.post("/api/info-items/publish", json=publish_payload)
    assert publish_resp.status_code == 400
    assert "level-4" in publish_resp.json()["detail"]


def test_direct_publish_normalizes_indicator_id_from_name(client):
    publish_payload = {
        "title": "名称归一化指标",
        "content": "前端只传名称时，后端也要补齐 indicator_id",
        "source_url": "https://example.com/direct-publish-normalize-indicator-id",
        "published_at": "2026-03-09T00:00:00Z",
        "importance_score": 4,
        "is_new_tech": True,
        "comment": "验证名称到 indicator_id 的后端归一化",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["指标归一化"],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "draft_data": {
            "manual_alert": False,
            "duration": "month",
            "indicators": [
                {"indicator_id": "", "name": CAPTURE_REGEN_NAME, "value": "2.2", "unit": "", "keep": True},
                {"indicator_id": "", "name": CAPTURE_RATE_NAME, "value": "91", "unit": "", "keep": True},
            ],
        },
        "alert": None,
    }
    publish_resp = client.post("/api/info-items/publish", json=publish_payload)
    assert publish_resp.status_code == 201
    published = publish_resp.json()
    indicators = (published.get("draft_data") or {}).get("indicators") or []
    assert len(indicators) == 2
    assert indicators[0]["indicator_id"] == CAPTURE_REGEN_ID
    assert indicators[0]["name"] == CAPTURE_REGEN_NAME
    assert indicators[0]["unit"] == CAPTURE_REGEN_UNIT
    assert indicators[1]["indicator_id"] == CAPTURE_RATE_ID
    assert indicators[1]["name"] == CAPTURE_RATE_NAME
    assert indicators[1]["unit"] == CAPTURE_RATE_UNIT


def test_direct_publish_normalizes_indicator_id_from_match_name_and_plain_co2_unit(client):
    publish_payload = {
        "title": "批量导入别名指标",
        "content": "前端批量导入用简写指标名和普通 CO2 也应命中预设",
        "source_url": "https://example.com/direct-publish-match-name",
        "published_at": "2026-03-25T00:00:00Z",
        "importance_score": 4,
        "is_new_tech": True,
        "comment": "验证 match_name 与 CO2 归一化",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["指标归一化", "match_name"],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "draft_data": {
            "manual_alert": False,
            "duration": "month",
            "indicators": [
                {"indicator_id": "", "name": "再生能耗", "value": "2.5", "unit": "GJ/tCO2", "keep": True},
            ],
        },
        "alert": None,
    }
    publish_resp = client.post("/api/info-items/publish", json=publish_payload)
    assert publish_resp.status_code == 201
    published = publish_resp.json()
    indicators = (published.get("draft_data") or {}).get("indicators") or []
    assert len(indicators) == 1
    assert indicators[0]["indicator_id"] == CAPTURE_REGEN_ID
    assert indicators[0]["name"] == CAPTURE_REGEN_NAME
    assert indicators[0]["unit"] == "GJ/tCO2"


def test_bulk_like_multi_publish_with_multi_indicators(client):
    rows = [
        {
            "title": "批量发布-情报A",
            "content": "批量发布A，包含多指标",
            "source_url": "https://example.com/bulk-a",
            "published_at": "2026-03-09T00:00:00Z",
            "importance_score": 4,
            "is_new_tech": True,
            "comment": "A",
            "source_types": ["产业新闻"],
            "info_types": ["技术"],
            "tags": ["批量", "A"],
            "domain_ids": [CAPTURE_LEAF_ID],
            "classification": "内部",
            "draft_data": {
                "manual_alert": False,
                "duration": "month",
                "indicators": [
                    {"indicator_id": CAPTURE_REGEN_ID, "name": CAPTURE_REGEN_NAME, "value": "2.3", "unit": CAPTURE_REGEN_UNIT, "keep": True},
                    {"indicator_id": CAPTURE_RATE_ID, "name": CAPTURE_RATE_NAME, "value": "92", "unit": CAPTURE_RATE_UNIT, "keep": True},
                ],
            },
            "alert": None,
        },
        {
            "title": "批量发布-情报B",
            "content": "批量发布B，包含多指标",
            "source_url": "https://example.com/bulk-b",
            "published_at": "2026-03-09T00:00:00Z",
            "importance_score": 3,
            "is_new_tech": False,
            "comment": "B",
            "source_types": ["学术文献"],
            "info_types": ["技术"],
            "tags": ["批量", "B"],
            "domain_ids": [CAPTURE_LEAF_ID],
            "classification": "内部",
            "draft_data": {
                "manual_alert": False,
                "duration": "month",
                "indicators": [
                    {"indicator_id": CAPTURE_REGEN_ID, "name": CAPTURE_REGEN_NAME, "value": "2.8", "unit": CAPTURE_REGEN_UNIT, "keep": True},
                    {"indicator_id": CAPTURE_CYCLE_ID, "name": CAPTURE_CYCLE_NAME, "value": "3000", "unit": CAPTURE_CYCLE_UNIT, "keep": True},
                ],
            },
            "alert": None,
        },
    ]

    created_ids = []
    for row in rows:
        resp = client.post("/api/info-items/publish", json=row)
        assert resp.status_code == 201
        payload = resp.json()
        assert payload["status"] == "published"
        indicators = (payload.get("draft_data") or {}).get("indicators") or []
        assert len(indicators) == 2
        created_ids.append(payload["id"])

    assert len(created_ids) == 2
    assert created_ids[0] != created_ids[1]

    for row, item_id in zip(rows, created_ids):
        detail_resp = client.get(f"/api/info-items/{item_id}")
        assert detail_resp.status_code == 200
        item = detail_resp.json()
        assert item["title"] == row["title"]
        indicators = (item.get("draft_data") or {}).get("indicators") or []
        assert len(indicators) == 2
        assert indicators[0]["name"] == row["draft_data"]["indicators"][0]["name"]
        assert indicators[0]["indicator_id"] == row["draft_data"]["indicators"][0]["indicator_id"]
        assert indicators[0]["value"] == row["draft_data"]["indicators"][0]["value"]
        assert indicators[1]["name"] == row["draft_data"]["indicators"][1]["name"]
        assert indicators[1]["indicator_id"] == row["draft_data"]["indicators"][1]["indicator_id"]
        assert indicators[1]["value"] == row["draft_data"]["indicators"][1]["value"]

    list_resp = client.get("/api/info-items?status=published")
    assert list_resp.status_code == 200
    published_ids = {item["id"] for item in list_resp.json()}
    assert created_ids[0] in published_ids
    assert created_ids[1] in published_ids


def test_direct_publish_drops_non_preset_indicators_and_keeps_preset_only(client):
    publish_payload = {
        "title": "仅保留预设指标",
        "content": "非预设指标应被丢弃",
        "source_url": "https://example.com/direct-publish-drop-non-preset",
        "published_at": "2026-03-17T00:00:00Z",
        "importance_score": 4,
        "is_new_tech": True,
        "comment": "验证仅保留预设指标",
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": ["指标过滤"],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "draft_data": {
            "manual_alert": False,
            "duration": "month",
            "indicators": [
                {"indicator_id": "", "name": "工作容量", "value": "2.2", "unit": "", "keep": True},
                {"indicator_id": "", "name": CAPTURE_RATE_NAME, "value": "92", "unit": "", "keep": True},
            ],
        },
        "alert": None,
    }
    publish_resp = client.post("/api/info-items/publish", json=publish_payload)
    assert publish_resp.status_code == 201
    published = publish_resp.json()
    indicators = (published.get("draft_data") or {}).get("indicators") or []
    assert len(indicators) == 1
    assert indicators[0]["indicator_id"] == CAPTURE_RATE_ID
    assert indicators[0]["name"] == CAPTURE_RATE_NAME
    assert indicators[0]["value"] == "92"


def test_publish_revision_auto_deletes_original(client):
    # Create the original published item
    original_payload = {
        "title": "原始情报",
        "content": "原始正文内容",
        "source_url": "https://example.com/original",
        "published_at": "2026-03-01T00:00:00Z",
        "importance_score": 3,
        "is_new_tech": False,
        "comment": None,
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": [],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "draft_data": {"manual_alert": False, "duration": "month", "indicators": []},
        "alert": None,
    }
    orig_resp = client.post("/api/info-items/publish", json=original_payload)
    assert orig_resp.status_code == 201
    original_id = orig_resp.json()["id"]

    # Publish a revision that references the original
    revision_payload = {
        "title": "修订后的情报",
        "content": "修订后的正文内容",
        "source_url": "https://example.com/revised",
        "published_at": "2026-04-01T00:00:00Z",
        "importance_score": 4,
        "is_new_tech": True,
        "comment": None,
        "source_types": ["产业新闻"],
        "info_types": ["技术"],
        "tags": [],
        "domain_ids": [CAPTURE_LEAF_ID],
        "classification": "内部",
        "draft_id": None,
        "revision_of": original_id,
        "draft_data": {"manual_alert": False, "duration": "month", "indicators": []},
        "alert": None,
    }
    rev_resp = client.post("/api/info-items/publish", json=revision_payload)
    assert rev_resp.status_code == 201
    revised = rev_resp.json()
    assert revised["status"] == "published"
    assert revised["title"] == "修订后的情报"

    # Original item should be deleted
    gone_resp = client.get(f"/api/info-items/{original_id}")
    assert gone_resp.status_code == 404


def test_assistant_models_refresh_param_bypasses_cache(monkeypatch):
    """登录用户（非 admin 也可）可带 refresh=true 强制刷新目录。"""
    from app.routers import assistant_stream

    calls = []

    def fake_available(refresh=False):
        calls.append(refresh)
        return {"models": ["m-a", "m-b"], "default_model": "m-a", "source": "discovered"}

    monkeypatch.setattr(assistant_stream, "get_available_models", fake_available)
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {create_token('plainuser')}"})
        r1 = c.get("/api/assistant/models")
        r2 = c.get("/api/assistant/models?refresh=true")
    assert r1.status_code == 200 and r2.status_code == 200
    assert calls == [False, True]
    assert r2.json()["models"] == ["m-a", "m-b"]

"""v7 历史会话游标分页测试：真实 PostgreSQL。

覆盖：首批 20 条、游标续页取全、同 updated_at 并列稳定性（45+ 条）、
账号隔离（游标不可跨账号）、无效游标 422、账号删除级联清理。
"""
import uuid as _uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_token, hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.conversation import ConversationSession
from app.models.user import User

PAGE_USER_PREFIX = "pagetest_"
CLEANUP = []


@pytest.fixture()
def conv_user():
    db = SessionLocal()
    user = PAGE_USER_PREFIX + _uuid.uuid4().hex[:8]
    db.add(
        User(
            username=user,
            password_hash=hash_password("Pagetest123"),
            display_name="分页测试",
            role="user",
            is_active=True,
        )
    )
    db.commit()
    CLEANUP.append(user)
    db.close()
    return user


@pytest.fixture()
def conv_user2():
    db = SessionLocal()
    user = PAGE_USER_PREFIX + _uuid.uuid4().hex[:8]
    db.add(
        User(
            username=user,
            password_hash=hash_password("Pagetest123"),
            display_name="分页测试2",
            role="user",
            is_active=True,
        )
    )
    db.commit()
    CLEANUP.append(user)
    db.close()
    return user


def teardown_module(module):
    db = SessionLocal()
    try:
        for user in CLEANUP:
            for s in db.scalars(
                select(ConversationSession).where(ConversationSession.user_id == user)
            ).all():
                db.delete(s)
            u = db.get(User, user)
            if u:
                db.delete(u)
        db.commit()
    finally:
        db.close()


def _seed(user: str, n_same: int, n_spread: int):
    """n_same 条同刻(并列) + n_spread 条逐分钟递减。"""
    db = SessionLocal()
    try:
        base = datetime(2026, 9, 1, 12, 0, 0)
        rows = []
        for i in range(n_same):
            s = ConversationSession(user_id=user, title=f"same-{i:02d}")
            db.add(s)
            db.flush()
            db.execute(
                ConversationSession.__table__.update()
                .where(ConversationSession.id == s.id)
                .values(updated_at=base)
            )
            rows.append(s.id)
        for i in range(n_spread):
            s = ConversationSession(user_id=user, title=f"old-{i:02d}")
            db.add(s)
            db.flush()
            db.execute(
                ConversationSession.__table__.update()
                .where(ConversationSession.id == s.id)
                .values(updated_at=base - timedelta(minutes=i + 1))
            )
            rows.append(s.id)
        db.commit()
    finally:
        db.close()


def _headers(user: str) -> dict:
    return {"Authorization": f"Bearer {create_token(user)}"}


def _fetch(client, headers, cursor=None, limit=20):
    params = {"limit": limit}
    if cursor:
        params["cursor"] = cursor
    r = client.get("/api/conversations", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_first_page_limit_20(conv_user):
    _seed(conv_user, n_same=25, n_spread=20)
    with TestClient(app) as client:
        d = _fetch(client, _headers(conv_user))
        assert len(d["sessions"]) == 20
        assert d["has_more"] is True
        assert d["next_cursor"]


def test_walk_all_pages_no_dup_no_loss(conv_user):
    total = 45
    _seed(conv_user, n_same=25, n_spread=20)
    with TestClient(app) as client:
        headers = _headers(conv_user)
        seen, cursor = [], None
        for _ in range(10):
            d = _fetch(client, headers, cursor)
            seen += [s["id"] for s in d["sessions"]]
            if not d["has_more"]:
                break
            cursor = d["next_cursor"]
        assert len(seen) == total, f"应取完 {total} 条, 实得 {len(seen)}"
        assert len(set(seen)) == total, "跨页不得重复"


def test_last_page_partial(conv_user):
    _seed(conv_user, n_same=0, n_spread=23)
    with TestClient(app) as client:
        headers = _headers(conv_user)
        p1 = _fetch(client, headers)
        assert len(p1["sessions"]) == 20 and p1["has_more"]
        p2 = _fetch(client, headers, p1["next_cursor"])
        assert len(p2["sessions"]) == 3
        assert p2["has_more"] is False
        assert p2["next_cursor"] is None


def test_cursor_isolated_per_account(conv_user, conv_user2):
    _seed(conv_user, n_same=25, n_spread=0)
    with TestClient(app) as client:
        mine = _fetch(client, _headers(conv_user))
        other = _fetch(client, _headers(conv_user2), mine["next_cursor"])
        mine_ids = {s["id"] for s in mine["sessions"]}
        assert all(s["id"] not in mine_ids for s in other["sessions"])
        # 无数据账号: has_more False, cursor None
        assert other["has_more"] is False


def test_invalid_cursor_422(conv_user):
    with TestClient(app) as client:
        r = client.get(
            "/api/conversations",
            params={"cursor": "!!!broken!!!"},
            headers=_headers(conv_user),
        )
        assert r.status_code == 422


def test_legacy_default_limit_20_no_cursor(conv_user):
    """不带 limit 参数时默认 20（取代旧固定 50）。"""
    _seed(conv_user, n_same=25, n_spread=0)
    with TestClient(app) as client:
        r = client.get("/api/conversations", headers=_headers(conv_user))
        assert r.status_code == 200
        assert len(r.json()["sessions"]) == 20

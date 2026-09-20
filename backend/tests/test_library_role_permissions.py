"""资料库三级角色权限矩阵：管理员 > ATSC 用户 > 普通用户。

- 普通用户（user）：仅可查看（列表/预览），不可上传/下载/删除
- ATSC 用户（atsc）：可上传/下载
- 管理员（admin）：可上传/下载/删除，并保留人工分类等管理操作
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_token, hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.user import User

CREDENTIALS = {
    "perm_admin": ("PermAdmin123", "admin"),
    "perm_atsc": ("PermAtsc123", "atsc"),
    "perm_user": ("PermUser123", "user"),
}


@pytest.fixture(scope="module", autouse=True)
def role_test_users():
    db = SessionLocal()
    try:
        for username, (password, role) in CREDENTIALS.items():
            existing = db.get(User, username)
            if existing:
                db.delete(existing)
                db.flush()
            db.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    display_name=f"权限测试 {username}",
                    role=role,
                    is_active=True,
                )
            )
        db.commit()
        yield
        for username in CREDENTIALS:
            existing = db.get(User, username)
            if existing:
                db.delete(existing)
        db.commit()
    finally:
        db.close()


def _login(username: str) -> dict:
    password, _ = CREDENTIALS[username]
    with TestClient(app) as c:
        resp = c.post("/api/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_headers():
    return _login("perm_admin")


@pytest.fixture(scope="module")
def atsc_headers():
    return _login("perm_atsc")


@pytest.fixture(scope="module")
def user_headers():
    return _login("perm_user")


def test_me_reports_each_role(admin_headers, atsc_headers, user_headers):
    with TestClient(app) as c:
        for headers, expected in [
            (admin_headers, "admin"),
            (atsc_headers, "atsc"),
            (user_headers, "user"),
        ]:
            resp = c.get("/api/auth/me", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["role"] == expected


def test_list_uploads_visible_to_all_roles(admin_headers, atsc_headers, user_headers):
    """查看（列表）对三级角色均开放。"""
    with TestClient(app) as c:
        for headers in (admin_headers, atsc_headers, user_headers):
            resp = c.get("/api/uploads?limit=1", headers=headers)
            assert resp.status_code == 200


def test_taxonomy_visible_to_all_roles(admin_headers, atsc_headers, user_headers):
    with TestClient(app) as c:
        for headers in (admin_headers, atsc_headers, user_headers):
            resp = c.get("/api/uploads/taxonomy", headers=headers)
            assert resp.status_code == 200


def test_upload_allowed_for_admin_and_atsc_denied_for_user(
    admin_headers, atsc_headers, user_headers
):
    """上传：管理员与 ATSC 用户可以通过权限校验（此处用空文件触达请求体校验层），普通用户 403。"""
    with TestClient(app) as c:
        for headers, expected in [
            (admin_headers, 422),   # 越过权限层后命中 files 字段缺失校验
            (atsc_headers, 422),
            (user_headers, 403),    # 权限层直接拒绝
        ]:
            resp = c.post("/api/uploads", headers=headers, files={})
            assert resp.status_code == expected, (headers, resp.text)


def test_download_denied_for_user(admin_headers, atsc_headers, user_headers):
    """下载原文件：管理员与 ATSC 用户可执行（随机 id 命中 404），普通用户 403。"""
    missing_id = str(uuid.uuid4())
    with TestClient(app) as c:
        for headers, expected in [
            (admin_headers, 404),
            (atsc_headers, 404),
            (user_headers, 403),
        ]:
            resp = c.get(f"/api/uploads/{missing_id}/download", headers=headers)
            assert resp.status_code == expected, (headers, resp.text)


def test_document_assets_denied_for_user(admin_headers, atsc_headers, user_headers):
    """Markdown/Chunk 等文档资产属于下载能力，普通用户 403。"""
    missing_id = str(uuid.uuid4())
    with TestClient(app) as c:
        for headers, expected in [
            (admin_headers, 404),
            (atsc_headers, 404),
            (user_headers, 403),
        ]:
            resp = c.get(f"/api/uploads/{missing_id}/assets/markdown", headers=headers)
            assert resp.status_code == expected, (headers, resp.text)


def test_delete_admin_only(admin_headers, atsc_headers, user_headers):
    """删除仅管理员；ATSC 用户与普通用户均 403。"""
    missing_id = str(uuid.uuid4())
    with TestClient(app) as c:
        for headers, expected in [
            (admin_headers, 404),
            (atsc_headers, 403),
            (user_headers, 403),
        ]:
            resp = c.delete(f"/api/uploads/{missing_id}", headers=headers)
            assert resp.status_code == expected, (headers, resp.text)


def test_classification_retry_admin_only(admin_headers, atsc_headers, user_headers):
    """人工分类/重试等资料管理操作仅管理员。"""
    missing_id = str(uuid.uuid4())
    with TestClient(app) as c:
        for headers, expected in [
            (admin_headers, 404),
            (atsc_headers, 403),
            (user_headers, 403),
        ]:
            resp = c.post(f"/api/uploads/{missing_id}/classification/retry", headers=headers)
            assert resp.status_code == expected, (headers, resp.text)


def test_users_api_accepts_atsc_role(admin_headers):
    """用户管理接口支持创建/编辑 ATSC 用户，并拒绝未知角色。"""
    username = "perm_atsc_tmp"
    with TestClient(app) as c:
        resp = c.post(
            "/api/users",
            headers=admin_headers,
            json={"username": username, "password": "TmpAtsc123", "role": "atsc"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] == "atsc"

        resp = c.patch(f"/api/users/{username}", headers=admin_headers, json={"role": "user"})
        assert resp.status_code == 200 and resp.json()["role"] == "user"
        resp = c.patch(f"/api/users/{username}", headers=admin_headers, json={"role": "atsc"})
        assert resp.status_code == 200 and resp.json()["role"] == "atsc"

        resp = c.patch(f"/api/users/{username}", headers=admin_headers, json={"role": "boss"})
        assert resp.status_code == 400

        resp = c.delete(f"/api/users/{username}", headers=admin_headers)
        assert resp.status_code in (200, 204)


def test_users_api_rejects_unknown_role_on_create(admin_headers):
    with TestClient(app) as c:
        resp = c.post(
            "/api/users",
            headers=admin_headers,
            json={"username": "perm_boss", "password": "Boss12345", "role": "boss"},
        )
        assert resp.status_code == 400

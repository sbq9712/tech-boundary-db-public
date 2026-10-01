"""GitHub 广度情报增量包导入通道（docs/design/github-incremental-dedup.md 契约）。

覆盖：包结构/完整性校验、t|d|u 三层去重（幂等重放/包内去重/撞库跳过）、
持久字段映射（含 sc/scd 评分）、POST /api/uploads 端到端（真实 PostgreSQL）。
"""
from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest

from app.core.security import hash_password
from app.db.session import SessionLocal, get_db
from app.main import app
from app.models.breadth_import_session import BreadthImportSession
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.user import User
from app.services.github_import import (
    GitHubPackageError,
    _read_package,
    import_github_package,
    note_for_counts,
    validate_github_filename,
)
from sqlalchemy import text

CLEANUP: list[str] = []


def _mk_upload(db, checksum=None, title="pkg.zip", section="breadth", source="github"):
    from app.models.uploaded_file import UploadedFile

    rec = UploadedFile(
        stored_filename=f"objects/xx/{uuid.uuid4().hex}.zip",
        original_filename="2026-09-27.zip",
        mime_type="application/zip",
        checksum_sha256=checksum or uuid.uuid4().hex,
        storage_status="stored",
        title=title,
        title_source="manual",
        primary_section=section,
        breadth_source=source,
        classification_status="classified",
        embedding_status="skipped",
        submitted_by="githubimport-test",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    CLEANUP.append(str(rec.id))
    return rec


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        for rid in CLEANUP:
            db.execute(text("DELETE FROM breadth_index_tasks WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM breadth_index_tasks WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM breadth_import_sessions WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM breadth_manual_records WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM uploaded_files WHERE id=:i"), {"i": rid})
        db.commit()
    finally:
        db.close()
    CLEANUP.clear()


@pytest.fixture(autouse=True)
def _fresh_caches():
    from app.services import github_import as gi

    gi._upstream_key_digests.cache_clear()
    yield
    gi._upstream_key_digests.cache_clear()


def _write_upstream_shards(root: Path, records: list[dict], data_version: str = "testdv1") -> Path:
    """构造最小上游分片目录（lite-part + manifest-data.js）。"""
    processed = root / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    payload = "window.__LITE_PARTS__=window.__LITE_PARTS__||[];window.__LITE_PARTS__.push(" \
              + json.dumps(records, ensure_ascii=False) + ");"
    (processed / "lite-part-0.js").write_text(payload, encoding="utf-8")
    (processed / "manifest-data.js").write_text(
        f'window.__MANIFEST_DATA__={{"meta":{{"data_version":"{data_version}"}}}};',
        encoding="utf-8",
    )
    return root


def _build_package(records: list[dict], date: str = "2026-09-27",
                   schema: str | None = None, date_field: str | None = None,
                   count_field: int | None = None, skip_members: list[str] | None = None,
                   corrupt_records: bool = False) -> bytes:
    records_json = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    if corrupt_records:
        records_json = records_json[:-1]  # 截断破坏 JSON
    manifest = {
        "schema": schema or "tech-boundary-feed-package/v1",
        "generator": "feed-pkg/v1",
        "date": date_field if date_field is not None else date,
        "record_count": count_field if count_field is not None else len(records),
        "records_sha256": hashlib.sha256(records_json.encode("utf-8")).hexdigest(),
        "data_version": "testdv1",
        "generated_at": "2026-09-28T05:00:00+08:00",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        members = {"manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
                   "records.json": records_json}
        for name, content in members.items():
            if skip_members and name in skip_members:
                continue
            zf.writestr(name, content)
    return buf.getvalue()


def _tmp_zip(tmp_path: Path, data: bytes) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "2026-09-27.zip"
    p.write_bytes(data)
    return p


# ── 文件名校验 ──

def test_validate_filename_rules():
    assert validate_github_filename("2026-09-27.zip") == ".zip"
    assert validate_github_filename("DAILY.ZIP") == ".zip"
    with pytest.raises(GitHubPackageError):
        validate_github_filename("../evil.zip")
    with pytest.raises(GitHubPackageError):
        validate_github_filename("a/b.zip")
    with pytest.raises(GitHubPackageError):
        validate_github_filename("records.json")
    with pytest.raises(GitHubPackageError):
        validate_github_filename(None)


# ── 包结构/完整性校验 ──

def test_read_package_rejects_structural_errors(tmp_path):
    # 非 zip
    p = tmp_path / "notazip.zip"
    p.write_bytes(b"plain text")
    with pytest.raises(GitHubPackageError, match="zip"):
        _read_package(p)
    # 缺成员
    good = _build_package([{"t": "A", "d": "2026-09-27", "u": "https://x"}])
    with pytest.raises(GitHubPackageError, match="缺少"):
        _read_package(_tmp_zip(tmp_path / "a", _build_package([], skip_members=["records.json"])))
    # schema 不符
    with pytest.raises(GitHubPackageError, match="schema"):
        _read_package(_tmp_zip(tmp_path / "b", _build_package(
            [{"t": "A", "d": "2026-09-27", "u": "https://x"}], schema="wrong/v9")))
    # sha 不符
    bad_sha = _build_package([{"t": "A", "d": "2026-09-27", "u": "https://x"}])
    import zipfile as _zf, io as _io
    buf = _io.BytesIO()
    with _zf.ZipFile(buf, "w") as zf:
        man = json.loads(json.dumps({"schema": "tech-boundary-feed-package/v1", "date": "2026-09-27",
                                     "record_count": 1, "records_sha256": "0" * 64}))
        zf.writestr("manifest.json", json.dumps(man))
        zf.writestr("records.json", json.dumps([{"t": "A", "d": "2026-09-27", "u": "https://x"}]))
    with pytest.raises(GitHubPackageError, match="校验失败"):
        _read_package(_tmp_zip(tmp_path / "c", buf.getvalue()))
    # count 不符
    with pytest.raises(GitHubPackageError, match="record_count"):
        _read_package(_tmp_zip(tmp_path / "d", _build_package(
            [{"t": "A", "d": "2026-09-27", "u": "https://x"}], count_field=5)))
    # 日期格式
    with pytest.raises(GitHubPackageError, match="date"):
        _read_package(_tmp_zip(tmp_path / "e", _build_package(
            [{"t": "A", "d": "2026-09-27", "u": "https://x"}], date="27/09/2026")))
    assert good  # 构造未报错


# ── 服务层导入全流程（真实 DB）──

def test_import_full_flow_counts_and_rows(tmp_path, monkeypatch):
    root = _write_upstream_shards(tmp_path / "upstream", [
        # 上游已有 K0（撞库目标）
        {"t": "上游已有情报", "d": "2026-09-20", "u": "https://upstream/1", "c": "零碳产业"},
    ])
    monkeypatch.setenv("BREADTH_DATA_PATH", str(root))

    records = [
        {"t": " 上游已有情报 ", "d": "2026-09-20", "u": "https://upstream/1", "b": "x"},   # 撞库（上游）
        {"t": "全新情报A", "d": "2026-09-27", "u": "https://new/a", "b": "正文A", "c": "零碳产业/能量转化",
         "i": "l", "a": "Nature", "lv": 2, "sc": "8.5", "scd": {"tech": 8, "market": 9},
         "kp": [{"name": "能量密度", "value": "400"}], "as": "AI摘要A"},
        {"t": "包内重复B", "d": "2026-09-27", "u": "https://dup/b"},
        {"t": "包内重复B", "d": "2026-09-27", "u": "https://dup/b"},
        {"t": "无URL记录C", "d": "2026-09-26", "u": ""},   # sha256 占位
    ]
    zip_path = _tmp_zip(tmp_path, _build_package(records))
    checksum = hashlib.sha256(zip_path.read_bytes()).hexdigest()

    db = SessionLocal()
    try:
        upload = _mk_upload(db, checksum=checksum)
        payload = import_github_package(db, upload, zip_path)

        assert payload["imported"] == 3, payload
        assert payload["skipped_duplicate"] == 1
        assert payload["skipped_upstream_conflict"] == 1
        assert payload["failed"] == 0
        assert payload["package_deduplicated"] is True
        assert payload["replayed"] is False
        assert payload["package_date"] == "2026-09-27"
        assert payload["record_count"] == 5

        rows = db.execute(text(
            "SELECT title, document_date, url, level, intelligence_type, source_name, "
            "score, score_detail, key_parameters, ai_summary FROM breadth_manual_records "
            "WHERE upload_id=:i"), {"i": str(upload.id)}).mappings().all()
        by_title = {r["title"]: r for r in rows}
        assert set(by_title) == {"全新情报A", "包内重复B", "无URL记录C"}

        a = by_title["全新情报A"]
        assert a["document_date"] == "2026-09-27"
        assert a["level"] == 2
        assert a["intelligence_type"] in ("l", "literature")
        assert a["source_name"] == "Nature"
        assert a["score"] == "8.5"
        assert a["score_detail"] == {"tech": 8, "market": 9}
        assert a["ai_summary"] == "AI摘要A"
        assert by_title["无URL记录C"]["url"].startswith("sha256:")
        # 撞库记录未入表
        assert "上游已有情报" not in by_title

        # ── 幂等重放：同 checksum 的新上传 → 回放计数，不新增行 ──
        upload2 = _mk_upload(db, checksum=checksum, title="pkg2.zip")
        payload2 = import_github_package(db, upload2, zip_path)
        assert payload2["replayed"] is True
        assert payload2["imported"] == 3
        total = db.execute(text(
            "SELECT count(*) FROM breadth_manual_records WHERE upload_id IN (:a, :b)"),
            {"a": str(upload.id), "b": str(upload2.id)}).scalar()
        assert total == 3

        # ── 撞库（库内既有记录）：同键第二条包跳过 ──
        records2 = [{"t": "全新情报A", "d": "2026-09-27", "u": "https://new/a"}]
        zip2 = _tmp_zip(tmp_path / "second", _build_package(records2, date="2026-09-28"))
        upload3 = _mk_upload(db, checksum=hashlib.sha256(zip2.read_bytes()).hexdigest(), title="p3.zip")
        p3 = import_github_package(db, upload3, zip2)
        assert p3["imported"] == 0
        assert p3["skipped_upstream_conflict"] == 1

        assert "导入 0 条" in note_for_counts(p3) and "撞库跳过 1" in note_for_counts(p3)
    finally:
        db.close()


# ── 端到端：POST /api/uploads（真实 DB + 临时上传目录 + 临时上游分片）──

@pytest.fixture()
def gh_admin():
    db = SessionLocal()
    uname = "ghimp_admin1"
    existing = db.get(User, uname)
    if existing:
        db.delete(existing)
        db.flush()
    db.add(User(username=uname, password_hash=hash_password("GHIMP1231"),
                display_name="GH import test", role="admin", is_active=True))
    db.commit()
    db.close()
    yield uname
    db = SessionLocal()
    u = db.get(User, uname)
    if u:
        db.delete(u)
    db.commit()
    db.close()


def test_post_upload_github_package_e2e(tmp_path, monkeypatch, gh_admin):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TECHDB_UPLOAD_DIR", str(tmp_path / "uploads"))
    root = _write_upstream_shards(tmp_path / "upstream", [])
    monkeypatch.setenv("TECHDB_BREADTH_INDEX_WORKER_ENABLED", "false")
    monkeypatch.setenv("BREADTH_DATA_PATH", str(root))

    records = [
        {"t": "端到端情报X", "d": "2026-09-27", "u": "https://e2e/x", "b": "正文", "c": "零碳产业",
         "sc": "7.8", "scd": {"tech": 7}, "lv": 1},
    ]
    zip_bytes = _build_package(records)

    with TestClient(app) as c:
        login = c.post("/api/auth/login", json={"username": gh_admin, "password": "GHIMP1231"})
        assert login.status_code == 200
        c.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})

        resp = c.post("/api/uploads",
                      files={"files": ("2026-09-27.zip", io.BytesIO(zip_bytes), "application/zip")},
                      data={"primary_section": "breadth", "breadth_source": "github"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["count"] == 1
        gi = body["github_import"]
        assert gi["imported"] == 1 and gi["failed"] == 0
        f = body["files"][0]
        assert f["title"] == "广度增量包 2026-09-27"
        assert f["document_date"] == "2026-09-27"
        assert f["status"] == "imported"
        assert "导入 1 条" in f["note"]
        assert f["breadth_source"] == "github"
        CLEANUP.append(f["id"])

        # 列表接口按 github 来源过滤可见
        lst = c.get("/api/uploads?section=breadth&breadth_source=github").json()
        assert any(x["id"] == f["id"] for x in lst["files"])
        assert lst["counts"]["github"] >= 1

        # manual-records 读侧：导入记录以短键透出（含 sc/scd）
        mr = c.get("/api/breadth/manual-records?limit=50").json()
        hit = [r for r in mr["records"] if r["t"] == "端到端情报X"]
        assert hit, "导入记录未出现在 manual-records 读侧"
        assert hit[0]["sc"] == "7.8"
        assert hit[0]["scd"] == {"tech": 7}
        assert hit[0]["a"] == "" or isinstance(hit[0]["a"], str)

        # 重复提交同一包（同字节）→ 幂等重放，不重复入表
        resp2 = c.post("/api/uploads",
                       files={"files": ("2026-09-27.zip", io.BytesIO(zip_bytes), "application/zip")},
                       data={"primary_section": "breadth", "breadth_source": "github"})
        assert resp2.status_code == 201, resp2.text
        gi2 = resp2.json()["github_import"]
        assert gi2["replayed"] is True
        assert gi2["imported"] == 1
        CLEANUP.append(resp2.json()["files"][0]["id"])

        mr2 = c.get("/api/breadth/manual-records?limit=100").json()
        hits = [r for r in mr2["records"] if r["t"] == "端到端情报X"]
        assert len(hits) == 1, "幂等重放产生了重复记录"

        # 非 zip 提交被拒
        resp3 = c.post("/api/uploads",
                       files={"files": ("records.json", io.BytesIO(b"{}"), "application/json")},
                       data={"primary_section": "breadth", "breadth_source": "github"})
        assert resp3.status_code == 400
        # 多文件提交被拒
        resp4 = c.post("/api/uploads",
                       files=[("files", ("a.zip", io.BytesIO(zip_bytes), "application/zip")),
                              ("files", ("b.zip", io.BytesIO(zip_bytes), "application/zip"))],
                       data={"primary_section": "breadth", "breadth_source": "github"})
        assert resp4.status_code == 400
        # 损坏包：解包失败 → 400 且不落库（不留孤儿 uploaded_files 行）
        before_count = c.get("/api/uploads?section=breadth&breadth_source=github&limit=1").json()["count"]
        bad = _build_package([{"t": "坏", "d": "2026-09-27", "u": "https://bad"}], corrupt_records=True)
        resp5 = c.post("/api/uploads",
                       files={"files": ("2026-09-27.zip", io.BytesIO(bad), "application/zip")},
                       data={"primary_section": "breadth", "breadth_source": "github"})
        assert resp5.status_code == 400
        after_count = c.get("/api/uploads?section=breadth&breadth_source=github&limit=1").json()["count"]
        assert after_count == before_count, "被拒包不应留下孤儿上传记录"

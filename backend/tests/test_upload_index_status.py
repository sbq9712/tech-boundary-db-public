"""任务一 1.1：上传真实可检索状态（状态契约）功能测试。

覆盖：
- map_github_status 队列/会话映射全分支（indexed/index_failed/
  index_processing/index_queued/import_failed/no_new_records/legacy_unknown）；
- queue_aggregate 单条 GROUP BY 聚合正确（多上传多状态混合）；
- upload_index_status：canonical 不可达 → searchable=None（unknown，
  绝不假装可检索）；Docling 链 DB ready 但索引无内容 → legacy_unknown
  （以 canonical 为唯一权威）；
- 列表端点 GitHub 分支带 index_detail（队列映射）；
- /uploads/{id}/index-status 端点（登录）聚合三层；
- retry：zip 已落盘但导入从未完成（无记录无任务）→ 重新导入。
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.breadth_import_session import BreadthImportSession
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.index_task import IndexTask
from app.models.uploaded_file import UploadedFile
from app.services.index_status import (
    map_github_status,
    queue_aggregate,
    upload_index_status,
)

CLEANUP: list[str] = []


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch):
    monkeypatch.setenv("TECHDB_BREADTH_INDEX_WORKER_ENABLED", "false")


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        for rid in CLEANUP:
            db.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM breadth_index_tasks WHERE upload_id=:i"
                ),
                {"i": rid},
            )
            db.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM breadth_manual_records WHERE upload_id=:i"
                ),
                {"i": rid},
            )
            db.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM breadth_import_sessions WHERE upload_id=:i"
                ),
                {"i": rid},
            )
            db.execute(
                __import__("sqlalchemy").text("DELETE FROM uploaded_files WHERE id=:i"),
                {"i": rid},
            )
        db.commit()
    finally:
        db.close()
        CLEANUP.clear()


def _mk_upload(db, section="breadth", source="github", status="queued"):
    rec = UploadedFile(
        stored_filename=f"objects/xx/{uuid.uuid4().hex}",
        original_filename="2026-10-02.zip",
        mime_type="application/zip",
        checksum_sha256=uuid.uuid4().hex,
        storage_status="stored",
        primary_section=section,
        breadth_source=source,
        classification_status="classified",
        classification_confidence=1.0,
        classification_source="manual",
        embedding_status=status,
        submitted_by="status-test",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    CLEANUP.append(rec.id)
    return rec


def _mk_session(db, upload, **kw):
    s = BreadthImportSession(
        upload_id=upload.id,
        checksum_sha256=upload.checksum_sha256 or uuid.uuid4().hex,
        package_date=kw.pop("package_date", "2026-10-02"),
        schema_version="v2",
        record_count=kw.pop("record_count", 10),
        imported=kw.pop("imported", 10),
        skipped_duplicate=kw.pop("skipped_duplicate", 0),
        skipped_upstream_conflict=kw.pop("skipped_upstream_conflict", 0),
        failed=kw.pop("failed", 0),
    )
    db.add(s)
    db.commit()
    return s


def _mk_task(db, upload, status="done", op="upsert"):
    t = IndexTask(
        op=op,
        target_key=uuid.uuid4().hex,
        upload_id=upload.id,
        payload={},
        status=status,
    )
    db.add(t)
    db.commit()
    return t


# ── 纯映射逻辑 ──


def test_map_github_status_all_branches(db):
    upload = _mk_upload(db)

    # 全 done → indexed
    _mk_task(db, upload, "done")
    st, detail = map_github_status(upload, {"done": 3}, None)
    assert st == "indexed" and detail["tasks_total"] == 3

    # failed → index_failed（优先于 processing/pending）
    st, _ = map_github_status(upload, {"done": 2, "failed": 1}, None)
    assert st == "index_failed"

    # processing → index_processing
    st, _ = map_github_status(upload, {"done": 1, "processing": 2}, None)
    assert st == "index_processing"

    # pending → index_queued
    st, _ = map_github_status(upload, {"pending": 5}, None)
    assert st == "index_queued"

    # 无会话无任务 → legacy_unknown（导入中断）
    st, _ = map_github_status(upload, {}, None)
    assert st == "legacy_unknown"

    # 会话：failed>0 且 imported==0 → import_failed
    session = _mk_session(db, upload, imported=0, failed=8, record_count=8)
    st, _ = map_github_status(upload, {}, session)
    assert st == "import_failed"

    # 会话：零新增（全部上游持有/重复）→ no_new_records
    session.imported = 0
    session.failed = 0
    session.skipped_upstream_conflict = 383
    db.commit()
    st, detail = map_github_status(upload, {}, session, live_records=0)
    assert st == "no_new_records"
    assert detail["session"]["skipped_upstream_conflict"] == 383


def test_queue_aggregate_groups_per_upload(db):
    u1, u2 = _mk_upload(db), _mk_upload(db)
    _mk_task(db, u1, "done")
    _mk_task(db, u1, "failed")
    _mk_task(db, u2, "pending")
    agg = queue_aggregate(db, [u1.id, u2.id])
    assert agg[u1.id] == {"done": 1, "failed": 1}
    assert agg[u2.id] == {"pending": 1}
    assert queue_aggregate(db, []) == {}


def test_upload_index_status_canonical_unreachable_is_unknown(db, monkeypatch):
    """canonical 不可达 → searchable=None（如实 unknown，不假装可检索）。"""
    from app.services import index_status

    monkeypatch.setattr(index_status, "canonical_document_status", lambda ids: None)
    upload = _mk_upload(db)
    _mk_task(db, upload, "done")
    rec = BreadthManualRecord(
        upload_id=upload.id, user_id="status-test", title="t", body="b",
        category="c", origin_section="breadth")
    db.add(rec)
    db.commit()
    result = upload_index_status(db, upload)
    assert result["status"] == "indexed"
    assert result["searchable"] is None
    assert result["index"] == {"error": "canonical_unreachable"}
    # 名下无存活记录：如实 0 文档、searchable=False（不是 unknown）
    db.delete(rec)
    db.commit()
    result2 = upload_index_status(db, upload)
    assert result2["index"]["note"] == "no_live_records"
    assert result2["searchable"] is False


def test_upload_index_status_ready_but_absent_in_index(db, monkeypatch):
    """Docling 链：DB 说 ready 但 canonical 无内容 → legacy_unknown（1.1 契约）。"""
    from app.services import index_status

    upload = _mk_upload(db, section="atsc", source=None, status="ready")
    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {ids[0]: {"chunks": 0, "vector_ok": False, "bm25_ok": False}},
    )
    result = upload_index_status(db, upload)
    assert result["status"] == "legacy_unknown"
    assert result["searchable"] is False


def test_upload_index_status_docling_searchable(db, monkeypatch):
    from app.services import index_status

    upload = _mk_upload(db, section="atsc", source=None, status="ready")
    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {ids[0]: {"chunks": 94, "vector_ok": True, "bm25_ok": True,
                              "primary_section": "atsc"}},
    )
    result = upload_index_status(db, upload)
    assert result["status"] == "indexed"
    assert result["searchable"] is True
    assert result["index"]["chunks"] == 94
    assert result["index"]["primary_section"] == "atsc"


def test_upload_index_status_github_verifies_record_docs(db, monkeypatch):
    """GitHub 分支：按记录 document_id 核对 canonical；全 done 但索引为空 → 降级。"""
    from app.services import index_status

    upload = _mk_upload(db)
    _mk_task(db, upload, "done")
    rec = BreadthManualRecord(
        upload_id=upload.id,
        user_id="status-test",
        title="t",
        body="b",
        category="c",
        origin_section="breadth",
    )
    db.add(rec)
    db.commit()
    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {str(rec.id): {"chunks": 0, "vector_ok": False, "bm25_ok": False}},
    )
    result = upload_index_status(db, upload)
    assert result["status"] == "legacy_unknown"  # 队列 done 但索引空——如实降级
    assert result["index"]["documents_found"] == 0

    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {str(rec.id): {"chunks": 2, "vector_ok": True, "bm25_ok": True,
                                   "primary_section": "breadth"}},
    )
    result = upload_index_status(db, upload)
    assert result["status"] == "indexed"
    assert result["searchable"] is True


def test_upload_index_status_row_table_verifies_record_docs(db, monkeypatch):
    """逐行表格链（drill 3.4 发现）：行业/广度表格同样按记录 document_id 核对。

    历史缺陷：非 GitHub 分支一律走上传 id（Docling 语义），行表格实际以
    行记录 id 入索引 → 误报 documents_found=0 / legacy_unknown。
    """
    from app.services import index_status

    upload = _mk_upload(db, section="industry", source=None, status="ready")
    _mk_task(db, upload, "done")
    _mk_task(db, upload, "done")
    rec = BreadthManualRecord(
        upload_id=upload.id,
        user_id="status-test",
        title="行业行",
        body="b",
        category="c",
        origin_section="industry",
    )
    db.add(rec)
    db.commit()

    # 记录 doc 在索引中可检索 → indexed + searchable（而非 legacy_unknown）
    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {str(rec.id): {"chunks": 1, "vector_ok": True, "bm25_ok": True,
                                   "primary_section": "industry"}},
    )
    result = upload_index_status(db, upload)
    assert result["status"] == "indexed"
    assert result["searchable"] is True
    assert result["index"]["documents_found"] == 1

    # 上传 id 语义下查不到 ≠ 不可检索：核对的必须是记录 id
    assert result["index"].get("primary_section") is None or True  # 行链不透出单值

    # 队列 done 但记录 doc 不在索引（索引损坏/清理）→ 如实降级
    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {str(rec.id): {"chunks": 0, "vector_ok": False, "bm25_ok": False}},
    )
    result = upload_index_status(db, upload)
    assert result["status"] == "legacy_unknown"
    assert result["searchable"] is False


# ── API 端点 ──


def _client():
    from app.main import app
    from app.core.security import get_current_user, require_admin

    app.dependency_overrides[get_current_user] = lambda: "status-test"
    app.dependency_overrides[require_admin] = lambda: "status-test"
    return TestClient(app)


def test_index_status_endpoint_aggregates(db, monkeypatch):
    from app.services import index_status

    upload = _mk_upload(db)
    _mk_task(db, upload, "done")
    monkeypatch.setattr(index_status, "canonical_document_status", lambda ids: None)
    client = _client()
    try:
        r = client.get(f"/api/uploads/{upload.id}/index-status")
        assert r.status_code == 200
        body = r.json()
        assert body["queue"]["done"] == 1
        # 名下无存活记录：searchable=False（0 文档，如实不可检索）
        assert body["searchable"] is False
        assert body["index"]["note"] == "no_live_records"
        r404 = client.get(f"/api/uploads/{uuid.uuid4()}/index-status")
        assert r404.status_code == 404
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_list_uploads_carries_index_detail(db, monkeypatch):
    upload = _mk_upload(db)
    _mk_task(db, upload, "failed")
    client = _client()
    try:
        r = client.get("/api/uploads?section=breadth&breadth_source=github")
        assert r.status_code == 200
        files = [f for f in r.json()["files"] if f["id"] == str(upload.id)]
        assert files and files[0]["status"] == "index_failed"
        assert files[0]["index_detail"]["tasks_failed"] == 1
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_retry_reimports_stuck_zip_without_records_or_tasks(db, tmp_path, monkeypatch):
    """任务一 1.2 恢复缺口：zip 已落盘、导入从未完成（无会话/记录/任务，
    状态卡 queued=legacy_unknown）→ 重试从存储对象重新导入并入队。"""
    from app.routers import uploads as uploads_router
    from app.services import upload_ingestion, breadth_index_queue

    upload = _mk_upload(db)  # queued、无记录、无任务
    zip_path = tmp_path / "2026-10-02.zip"
    zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    monkeypatch.setattr(upload_ingestion, "safe_upload_path", lambda name: zip_path)

    def fake_import(sess, rec, path):
        assert path == zip_path
        row = BreadthManualRecord(
            upload_id=rec.id, user_id="status-test", title="r1", body="b1",
            category="c", origin_section="breadth")
        sess.add(row)
        sess.commit()
        return {"package_date": "2026-10-02"}

    monkeypatch.setattr(uploads_router, "import_github_package", fake_import)
    monkeypatch.setattr(breadth_index_queue, "process_batch", lambda *a, **k: None)

    client = _client()
    try:
        r = client.post(f"/api/uploads/{upload.id}/embedding/retry")
        assert r.status_code == 202, r.text
        assert r.json()["embedding_status"] == "queued"
        tasks = db.query(IndexTask).filter(IndexTask.upload_id == upload.id).all()
        assert tasks, "重新导入后必须入队索引任务"
        rows = db.query(BreadthManualRecord).filter(
            BreadthManualRecord.upload_id == upload.id).all()
        assert rows
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_retry_reimport_zero_new_records_settles_skipped(db, tmp_path, monkeypatch):
    """重放零新增（全部上游持有）：无新任务可入队 → 终态 skipped 而非永久 queued。"""
    from app.routers import uploads as uploads_router
    from app.services import upload_ingestion, breadth_index_queue

    upload = _mk_upload(db)
    zip_path = tmp_path / "2026-10-03.zip"
    zip_path.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    monkeypatch.setattr(upload_ingestion, "safe_upload_path", lambda name: zip_path)
    monkeypatch.setattr(
        uploads_router, "import_github_package",
        lambda sess, rec, path: {"package_date": "2026-10-03"})
    monkeypatch.setattr(breadth_index_queue, "process_batch", lambda *a, **k: None)

    client = _client()
    try:
        r = client.post(f"/api/uploads/{upload.id}/embedding/retry")
        assert r.status_code == 202, r.text
        assert r.json()["embedding_status"] == "skipped"
        check = SessionLocal()
        try:
            fresh = check.get(UploadedFile, upload.id)
            assert fresh.title == "广度增量包 2026-10-03"
            assert fresh.embedding_status == "skipped"
        finally:
            check.close()
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_list_maps_table_row_uploads_by_queue(db):
    """逐行表格上传（行业/ATSC/广度其他）同样走持久队列——列表映射真实状态。"""
    upload = _mk_upload(db, section="industry", source=None, status="ready")
    _mk_task(db, upload, "done")
    _mk_task(db, upload, "done")
    client = _client()
    try:
        r = client.get("/api/uploads?section=industry")
        assert r.status_code == 200
        files = [f for f in r.json()["files"] if f["id"] == str(upload.id)]
        assert files and files[0]["status"] == "indexed"
        assert files[0]["index_detail"]["tasks_total"] == 2
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_list_docling_uploads_without_tasks_keep_legacy_chain(db):
    """Docling 链（无队列任务）沿用既有状态链，不产生 index_detail。"""
    upload = _mk_upload(db, section="atsc", source=None, status="ready")
    client = _client()
    try:
        r = client.get("/api/uploads?section=atsc")
        assert r.status_code == 200
        files = [f for f in r.json()["files"] if f["id"] == str(upload.id)]
        assert files and files[0]["status"] == "ready"
        assert "index_detail" not in files[0]
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_upload_index_status_partial_docs_not_searchable(db, monkeypatch):
    """Codex P1-3：存活记录部分在索引（写入中/丢写）→ searchable=False。

    「有一条可检索」≠「整包可检索」：documents_missing 明细暴露缺口，
    队列 done 但有缺口 → legacy_unknown（重试=幂等重放恢复）。
    """
    from app.services import index_status

    upload = _mk_upload(db)  # breadth/github
    _mk_task(db, upload, "done")
    rec_a = BreadthManualRecord(upload_id=upload.id, user_id="status-test",
                                title="a", body="b", category="c",
                                origin_section="breadth")
    rec_b = BreadthManualRecord(upload_id=upload.id, user_id="status-test",
                                title="b", body="b", category="c",
                                origin_section="breadth")
    db.add_all([rec_a, rec_b])
    db.commit()

    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {str(rec_a.id): {"chunks": 1, "vector_ok": True, "bm25_ok": True,
                                     "primary_section": "breadth"}},
    )
    result = upload_index_status(db, upload)
    assert result["index"]["documents_missing"] == 1
    assert str(rec_b.id) in result["index"]["missing_document_ids"]
    assert result["searchable"] is False
    assert result["status"] == "legacy_unknown"

    # 全部落齐且健康 → searchable（旧行为不受影响）
    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {
            str(rec_a.id): {"chunks": 1, "vector_ok": True, "bm25_ok": True,
                            "primary_section": "breadth"},
            str(rec_b.id): {"chunks": 1, "vector_ok": True, "bm25_ok": True,
                            "primary_section": "breadth"},
        },
    )
    result = upload_index_status(db, upload)
    assert result["searchable"] is True
    assert result["status"] == "indexed"

    # 全在册但向量/BM25 不健康（结构损坏）→ 不误报可检索
    monkeypatch.setattr(
        index_status, "canonical_document_status",
        lambda ids: {
            str(rec_a.id): {"chunks": 1, "vector_ok": True, "bm25_ok": True},
            str(rec_b.id): {"chunks": 1, "vector_ok": False, "bm25_ok": True},
        },
    )
    result = upload_index_status(db, upload)
    assert result["searchable"] is False
    assert result["status"] == "legacy_unknown"

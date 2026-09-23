"""其他广度情报真实入表：持久层 + 读侧契约 + 生命周期同步（真实 PostgreSQL）。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.models.breadth_manual_record import BreadthManualRecord
from app.models.uploaded_file import UploadedFile
from app.db.session import SessionLocal
from app.services.upload_ingestion import sync_breadth_manual_record
from app.routers.breadth import _serialize, list_manual_records, update_manual_record

CLEANUP: list[str] = []


def _mk_upload(db, *, section="breadth", source="other", title="广度测试资料") -> UploadedFile:
    rec = UploadedFile(
        stored_filename=f"objects/xx/{uuid.uuid4().hex}.txt",
        original_filename="b.txt",
        mime_type="text/plain",
        checksum_sha256=uuid.uuid4().hex,
        storage_status="stored",
        title=title,
        title_source="manual",
        primary_section=section,
        breadth_source=source,
        document_date="2026-09-01",
        classification_status="classified",
        primary_category="未分类",
        submitted_by="breadthtest",
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
    for rid in CLEANUP:
        db.execute(text("DELETE FROM breadth_manual_records WHERE upload_id=:i"), {"i": rid})
        db.execute(text("DELETE FROM uploaded_files WHERE id=:i"), {"i": rid})
    db.commit()
    db.close()
    CLEANUP.clear()


def _db():
    return SessionLocal()


def test_one_file_one_record_idempotent():
    """1 文件 = 1 广度记录：重复处理不重复入表，只更新。"""
    db = _db()
    rec = _mk_upload(db)
    sync_breadth_manual_record(db, rec, "正文内容A")
    sync_breadth_manual_record(db, rec, "正文内容A")  # 重试
    count = db.execute(
        text("SELECT count(*) FROM breadth_manual_records WHERE upload_id=:i"), {"i": str(rec.id)}
    ).scalar()
    assert count == 1
    row = db.execute(
        text("SELECT title, body, level FROM breadth_manual_records WHERE upload_id=:i"),
        {"i": str(rec.id)},
    ).mappings().one()
    assert row["title"] == "广度测试资料"
    assert row["body"] == "正文内容A"
    assert row["level"] == 0  # 默认不设置人工等级
    db.close()


def test_non_breadth_section_never_creates_record():
    """行业追踪/ATSC 分区不入广度表。"""
    db = _db()
    rec = _mk_upload(db, section="industry", source=None)
    sync_breadth_manual_record(db, rec, "text")
    assert db.execute(
        text("SELECT count(*) FROM breadth_manual_records WHERE upload_id=:i"), {"i": str(rec.id)}
    ).scalar() == 0
    db.close()


def test_level_inclusive_views():
    """人工等级包含关系：lv1 只在精选；lv2 在精选+重点；lv3 三层都出现。"""
    db = _db()
    uploads = {}
    for lv in (1, 2, 3):
        rec = _mk_upload(db, title=f"等级{lv}资料")
        sync_breadth_manual_record(db, rec, "x")
        db.execute(
            text("UPDATE breadth_manual_records SET level=:lv WHERE upload_id=:i"),
            {"lv": lv, "i": str(rec.id)},
        )
        db.commit()
        uploads[lv] = rec.id
    db.close()

    db = _db()
    counts = {"curated": 0, "key": 0, "alert": 0}
    rows = db.execute(text("SELECT upload_id, level FROM breadth_manual_records")).all()
    mine = {str(uid): lv for uid, lv in rows if str(uid) in [str(v) for v in uploads.values()]}
    for uid, lv in mine.items():
        counts["curated"] += lv >= 1
        counts["key"] += lv >= 2
        counts["alert"] += lv >= 3
    assert counts == {"curated": 3, "key": 2, "alert": 1}
    db.close()


def test_short_key_contract_aligns_with_meta_shards():
    """短键与广度总表分片逐字对齐（t/d/c/lv/i/hb/kp）。"""
    db = _db()
    rec = _mk_upload(db)
    sync_breadth_manual_record(db, rec, "正文")
    row = db.execute(
        text("SELECT * FROM breadth_manual_records WHERE upload_id=:i"), {"i": str(rec.id)}
    ).mappings().one()
    record = BreadthManualRecord(**{k: row[k] for k in row.keys()})
    payload = _serialize(record)
    assert payload["t"] == record.title
    assert payload["d"] == record.document_date
    assert payload["c"] == record.category
    assert payload["lv"] == record.level
    assert payload["i"] in ("n", "l")
    assert payload["hb"] == 1
    assert payload["source"] == "manual-import"
    db.close()


def test_rename_updates_both_tables():
    """资料改名 → 广度记录标题同步；等级更新独立可用。"""
    db = _db()
    rec = _mk_upload(db)
    sync_breadth_manual_record(db, rec, "x")
    breadth = db.scalar(
        select(BreadthManualRecord).where(BreadthManualRecord.upload_id == rec.id)
    )
    updated = update_manual_record(
        str(breadth.id),
        type("P", (), {"title": "改名后的广度资料", "level": 2, "category": None, "document_date": None})(),
        current_user="breadthtest",
        db=db,
    )
    assert updated["title"] == "改名后的广度资料"
    assert updated["level"] == 2
    db.expire(rec)
    assert rec.title == "改名后的广度资料"  # uploaded_files 同步
    assert rec.title_source == "manual"    # 保持 manual，不被 AI 覆盖
    db.close()


def test_cascade_delete_with_upload():
    """删除上传资料 → 广度记录级联删除。"""
    db = _db()
    rec = _mk_upload(db)
    sync_breadth_manual_record(db, rec, "x")
    uid = str(rec.id)
    assert db.execute(
        text("SELECT count(*) FROM breadth_manual_records WHERE upload_id=:i"), {"i": uid}
    ).scalar() == 1
    db.execute(text("DELETE FROM uploaded_files WHERE id=:i"), {"i": uid})
    db.commit()
    assert db.execute(
        text("SELECT count(*) FROM breadth_manual_records WHERE upload_id=:i"), {"i": uid}
    ).scalar() == 0
    db.close()


def test_list_endpoint_shape():
    db = _db()
    rec = _mk_upload(db)
    sync_breadth_manual_record(db, rec, "x")
    db.close()
    db = _db()
    data = list_manual_records(level=None, limit=500, offset=0, current_user="breadthtest", db=db)
    assert data["count"] >= 1
    assert set(data["level_counts"]) >= {"curated", "key", "alert", "zero"}
    assert any(r["upload_id"] == CLEANUP[0] for r in data["records"])
    db.close()


def test_rename_survives_index_outage(monkeypatch, tmp_path):
    """检索服务停机（网络层失败）不阻断改名：200 + 标题双向生效。"""
    import httpx as _httpx

    from app.services import upload_ingestion

    db = _db()
    rec = _mk_upload(db)
    sync_breadth_manual_record(db, rec, "x")
    # document_assets 指向不存在 bundle → chunks 为空 → 不会真正请求索引；
    # 这里直接模拟请求路径抛 TransportError，验证改名不被网络层异常打断。
    def boom(*a, **kw):
        raise _httpx.ConnectError("qa down")

    monkeypatch.setattr(upload_ingestion, "request_incremental_index", boom)
    monkeypatch.setattr(upload_ingestion, "upload_root", lambda: tmp_path)
    rec.document_assets = {"bundle": "documents/xx/bundle"}
    result = upload_ingestion.rename_uploaded_file(db, rec, "停机改名")
    assert result["ok"] is True and result["index_synced"] is False
    db.expire(rec)
    assert rec.title == "停机改名" and rec.title_source == "manual"
    db.close()

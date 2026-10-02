"""任务二 2.1：数据源归属贯通——功能测试。

覆盖：
- 行记录三入口 origin_section 写入（breadth/industry/atsc）；
- feed 通道（GitHub 包）记录 origin_section=breadth；
- sync_breadth_manual_record 行业/ATSC 同步记录归属原栏目；
- 队列 _upsert_payload：chunk_metadata.primary_section/source 按栏目落值，
  source_type 不再统一 breadth-import；
- Docling request_incremental_index 注入 primary_section/source；
- canonical-qa IncrementalIndex.patch_document_metadata/documents_metadata
  （锁内原位更新 + 无归属文档清单）。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.uploaded_file import UploadedFile
from app.services.table_rows import import_rows, parse_table

CLEANUP: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        for rid in CLEANUP:
            db.execute(text("DELETE FROM breadth_index_tasks WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM breadth_manual_records WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM uploaded_files WHERE id=:i"), {"i": rid})
        db.execute(text("DELETE FROM breadth_manual_records WHERE user_id='attr-test'"))
        db.commit()
    finally:
        db.close()
        CLEANUP.clear()


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


def _mk_upload(db, filename, section, source="other"):
    rec = UploadedFile(
        stored_filename=f"objects/xx/{uuid.uuid4().hex}",
        original_filename=filename,
        mime_type="text/csv",
        checksum_sha256=uuid.uuid4().hex,
        storage_status="stored",
        title=filename,
        title_source="manual",
        primary_section=section,
        breadth_source=source,
        classification_status="classified",
        embedding_status="queued",
        submitted_by="attr-test",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    CLEANUP.append(str(rec.id))
    return rec


def test_row_import_sets_origin_section_per_entry(db):
    """行业/ATSC 逐行导入记录归属原栏目（同步广度只改展示）。"""
    for section in ("breadth", "industry", "atsc"):
        data = f"标题,情报类型\n{section}情报,新闻\n".encode("utf-8")
        upload = _mk_upload(db, f"{section}.csv", section)
        sheets = parse_table(data, f"{section}.csv")
        stats = import_rows(
            db, upload, sheets, {"title": "标题", "type": "情报类型"},
            fallback_date=None, category_fallback=None,
            in_breadth_nav=(section == "breadth"),
            require_type=(section == "breadth"),
            origin_section=section)
        db.commit()
        assert stats["imported"] == 1
        row = db.scalars(
            __import__("sqlalchemy").select(BreadthManualRecord).where(
                BreadthManualRecord.upload_id == upload.id)).one()
        assert row.origin_section == section
        assert row.in_breadth_nav is (section == "breadth")


def test_queue_payload_carries_section_attribution(db):
    """_upsert_payload：chunk_metadata.primary_section/source + 顶层 source_type。"""
    from app.services.breadth_index_queue import _upsert_payload
    upload = _mk_upload(db, "ind.csv", "industry")
    rec = BreadthManualRecord(
        upload_id=upload.id, user_id="attr-test", title="行业甲",
        document_date="2026-09-01", url="https://a/1", body="正文",
        intelligence_type="news", origin_section="industry", stable_id="x" * 16)
    db.add(rec)
    db.commit()
    payload = _upsert_payload(rec)
    assert payload["source_type"] == "industry-import"
    for chunk in payload["chunks"]:
        md = chunk["metadata"]
        assert md["primary_section"] == "industry"
        assert md["source"] == "industry-import"
    # 旧行 origin_section=None → 兜底 breadth（回填脚本收敛）
    rec2 = BreadthManualRecord(
        upload_id=upload.id, user_id="attr-test", title="旧记录",
        body="旧正文", intelligence_type="news")
    db.add(rec2)
    db.commit()
    p2 = _upsert_payload(rec2)
    assert p2["source_type"] == "breadth-import"
    assert p2["chunks"][0]["metadata"]["primary_section"] == "breadth"


def test_feed_records_get_breadth_section(db):
    """GitHub 包记录（feed_key_digest 非空）归属 breadth。"""
    upload = _mk_upload(db, "pkg.zip", "breadth", source="github")
    from app.services.github_import import _row_fields
    fields = _row_fields(
        {"t": "包记录", "d": "2026-09-01", "u": "https://a/2", "b": "正文",
         "id": "a" * 16, "key": "包记录|2026-09-01|https://a/2", "v": 1},
        upload.id, "attr-test", 1)
    assert fields["origin_section"] == "breadth"
    rec = BreadthManualRecord(**fields)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    assert rec.origin_section == "breadth"


def test_docling_index_payload_injects_section(monkeypatch):
    """request_incremental_index 注入 primary_section/source 到 chunk metadata。"""
    import app.services.upload_ingestion as ui
    captured = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"status": "ready", "chunk_count": 1}

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["payload"] = json
            return _Resp()

    monkeypatch.setattr(ui.httpx, "Client", _Client)
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://qa")
    upload = UploadedFile(
        id=uuid.uuid4(), stored_filename="s", original_filename="报告.pdf",
        mime_type="application/pdf", checksum_sha256="c" * 64,
        storage_status="stored", title="报告", title_source="manual",
        primary_section="atsc", breadth_source="", classification_status="classified",
        embedding_status="queued", submitted_by="attr-test")
    chunks = [{"chunk_id": "c1", "document_id": str(upload.id), "text": "正文",
               "metadata": {"document_id": str(upload.id)}}]
    ui.request_incremental_index(upload, chunks)
    # v7（0023）契约：上传链负载不携带 source_type（白名单剥离）——
    # 归属经 chunk metadata 贯通（任务二 2.1）。
    assert "source_type" not in captured["payload"]
    assert captured["payload"]["chunks"][0]["metadata"]["primary_section"] == "atsc"
    assert captured["payload"]["chunks"][0]["metadata"]["source"] == "atsc-import"


def test_incremental_index_patch_and_documents_metadata(tmp_path, monkeypatch):
    """canonical-qa 侧：锁内原位 patch + 无归属文档清单（离线单元）。"""
    import sys
    qa = str(tmp_path / "qa")
    monkeypatch.setenv("TECHDB_QA_INCREMENTAL_INDEX_PATH", str(tmp_path / "index.pkl"))
    monkeypatch.syspath_prepend(qa)
    import importlib
    ii_path = str(__import__("pathlib").Path(
        __file__).resolve().parents[2] / "services" / "canonical-qa" / "qa-backend")
    sys.path.insert(0, ii_path)
    try:
        incremental_index = importlib.import_module("incremental_index")
    except ImportError:
        pytest.skip("canonical-qa sources unavailable")
    ii = incremental_index.IncrementalIndex(
        __import__("pathlib").Path(tmp_path) / "index.pkl",
        lambda texts: __import__("numpy").zeros((len(texts), 4)))
    # 手工构造两条 meta（绕过嵌入）：一条有归属一条没有
    import numpy as np
    with ii._state_lock:
        ii.meta = [
            {"key": "a-0", "document_id": "doc-a", "chunk_metadata": {
                "record_key_sha": "k1", "content_sha": "c1", "primary_section": "industry"}},
            {"key": "b-0", "document_id": "doc-b", "chunk_metadata": {
                "record_key_sha": "k2", "content_sha": "c2"}},
        ]
        ii.embeddings = np.zeros((2, 4))
        ii.corpus_tokens = [["行", "业"], ["广", "度"]]
        ii.loaded = True
    docs = ii.documents_metadata()
    assert docs["doc-a"]["chunks"] == 1
    assert docs["doc-a"]["primary_section"] == "industry"
    assert docs["doc-b"]["primary_section"] is None
    import asyncio
    patched = asyncio.run(ii.patch_document_metadata("doc-b", {"primary_section": "atsc"}))
    assert patched == 1
    docs2 = ii.documents_metadata()
    assert docs2["doc-b"]["primary_section"] == "atsc"
    patched0 = asyncio.run(ii.patch_document_metadata("doc-none", {"primary_section": "atsc"}))
    assert patched0 == 0  # 幂等：不在索引的文档零副作用

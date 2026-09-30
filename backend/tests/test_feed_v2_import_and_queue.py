"""feed-pkg/v2 变化包导入 + 广度问答索引持久队列（四节链路测试）。

覆盖（验收 5/10/11 相关）：
- ADD/UPDATE/DELETE 应用、旧不覆新（版本比较）、幂等重放；
- DELETE 不误删人工/其他来源记录（保护）；
- 私有字段白名单剥离（record_json 只存公开字段）；
- zip 安全：重复成员/恶意路径/超大成员/成员数超限拒绝；
- 索引任务：入队 → process_batch 执行（mock canonical-qa）→ 上传状态聚合；
  失败重试与退避；DELETE 任务调用索引删除；
- 表格逐行：CSV/XLSX 解析、列映射、逐行入库、去重、溯源 source_ref。
"""
from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.uploaded_file import UploadedFile
from app.services import breadth_index_queue as bq
from app.services import github_import as gi
from app.services.github_import import (
    GitHubPackageError,
    _read_package,
    import_github_package,
    note_for_counts,
)

CLEANUP: list[str] = []


# ── feed 侧同构工具（与 scripts/build_feed_package.py 对齐） ──────────────


def _stable_id(t: str, d: str, u: str) -> str:
    raw = json.dumps([t, d, u], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _content_hash(rec: dict) -> str:
    payload = {k: rec.get(k) for k in sorted(k for k in rec if k != "id")}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _norm(rec: dict) -> dict:
    out = {k: rec.get(k) for k in gi.PUBLIC_FIELDS if k in rec}
    u = str(out.get("u", "") or "")
    out["u"] = u if u else "sha256:" + _content_hash(rec)[:16]
    out["id"] = _stable_id(str(out.get("t", "")), str(out.get("d", "")), str(out.get("u", "")))
    return out


def _build_v2(
    records: list[dict],
    changes: list[dict],
    *,
    date: str = "2026-09-28",
    versions_marker: dict | None = None,
    dup_member: bool = False,
    evil_member: bool = False,
    huge_member: bool = False,
) -> bytes:
    out_records = [
        r for r in records if any(
            c["op"] in ("ADD", "UPDATE") and c["id"] == r.get("id") for c in changes
        )
    ]
    records_json = json.dumps(out_records, ensure_ascii=False, separators=(",", ":"))
    manifest = {
        "schema": "tech-boundary-feed-package/v2",
        "generator": "feed-pkg/v2",
        "mode": "changes",
        "date": date,
        "record_count": len(out_records),
        "change_count": len(changes),
        "added": sum(1 for c in changes if c["op"] == "ADD"),
        "updated": sum(1 for c in changes if c["op"] == "UPDATE"),
        "deleted": sum(1 for c in changes if c["op"] == "DELETE"),
        "records_sha256": hashlib.sha256(records_json.encode("utf-8")).hexdigest(),
        "data_version": "dv-test-v2",
        "generated_at": "2026-09-28T05:00:00+08:00",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("records.json", records_json)
        zf.writestr("changes.json", json.dumps(changes, ensure_ascii=False))
        if dup_member:
            zf.writestr("records.json", "[]")
        if evil_member:
            zf.writestr("../evil.json", "x")
        if huge_member:
            zf.writestr("huge.bin", b"x" * (gi.MAX_MEMBER_BYTES + 1))
    return buf.getvalue()


def _tmp_zip(tmp_path: Path, data: bytes, name: str = "pkg.zip") -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _mk_upload(db, checksum=None, section="breadth", source="github", title="pkg.zip"):
    rec = UploadedFile(
        stored_filename=f"objects/xx/{uuid.uuid4().hex}.zip",
        original_filename="2026-09-28.zip",
        mime_type="application/zip",
        checksum_sha256=checksum or uuid.uuid4().hex,
        storage_status="stored",
        title=title,
        title_source="manual",
        primary_section=section,
        breadth_source=source,
        classification_status="classified",
        embedding_status="queued",
        submitted_by="feedv2-test",
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
            db.execute(text("DELETE FROM breadth_import_sessions WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM breadth_manual_records WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM uploaded_files WHERE id=:i"), {"i": rid})
            db.execute(text("DELETE FROM breadth_feed_tombstones WHERE upload_id=:i"), {"i": rid})
        db.execute(text(
            "DELETE FROM breadth_manual_records WHERE user_id='feedv2-test'"
        ))
        db.execute(text(
            "DELETE FROM breadth_manual_records WHERE user_id='feedv2-test'"
        ))
        db.commit()
    finally:
        db.close()
        CLEANUP.clear()


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch):
    monkeypatch.setenv("TECHDB_BREADTH_INDEX_WORKER_ENABLED", "false")


# ── 校验与 zip 安全 ───────────────────────────────────────────────────────


def test_v2_requires_changes_json(tmp_path):
    rec = _norm({"t": "x", "d": "2026-09-28", "u": "https://x/1"})
    data = _build_v2([rec], [], date="2026-09-28")
    # 去掉 changes.json → 拒绝
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.namelist():
            if item != "changes.json":
                zout.writestr(item, zin.read(item))
    with pytest.raises(GitHubPackageError):
        _read_package(_tmp_zip(tmp_path, buf.getvalue()))


def test_v2_id_tampering_rejected(tmp_path):
    rec = _norm({"t": "x", "d": "2026-09-28", "u": "https://x/1"})
    rec["id"] = "0123456789abcdef"  # 与 t|d|u 不一致
    data = _build_v2([rec], [{"op": "ADD", "id": rec["id"], "key": "x|2026-09-28|https://x/1", "v": 1}])
    with pytest.raises(GitHubPackageError):
        _read_package(_tmp_zip(tmp_path, data))


def test_v2_dup_member_rejected(tmp_path):
    rec = _norm({"t": "x", "d": "2026-09-28", "u": "https://x/1"})
    data = _build_v2([rec], [], dup_member=True)
    with pytest.raises(GitHubPackageError):
        _read_package(_tmp_zip(tmp_path, data))


def test_v2_evil_path_rejected(tmp_path):
    rec = _norm({"t": "x", "d": "2026-09-28", "u": "https://x/1"})
    data = _build_v2([rec], [], evil_member=True)
    with pytest.raises(GitHubPackageError):
        _read_package(_tmp_zip(tmp_path, data))


def test_v2_oversized_member_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(gi, "MAX_MEMBER_BYTES", 1024)
    rec = _norm({"t": "x", "d": "2026-09-28", "u": "https://x/1"})
    data = _build_v2([rec], [], huge_member=True)
    with pytest.raises(GitHubPackageError):
        _read_package(_tmp_zip(tmp_path, data))


def test_v2_count_mismatch_rejected(tmp_path):
    rec = _norm({"t": "x", "d": "2026-09-28", "u": "https://x/1"})
    changes = [{"op": "ADD", "id": rec["id"], "key": "x|2026-09-28|https://x/1", "v": 1}]
    data = _build_v2([rec], changes)
    # 篡改 manifest.added
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.namelist():
            content = zin.read(item)
            if item == "manifest.json":
                man = json.loads(content)
                man["added"] = 99
                content = json.dumps(man).encode()
            zout.writestr(item, content)
    with pytest.raises(GitHubPackageError):
        _read_package(_tmp_zip(tmp_path, buf.getvalue()))


# ── 应用语义：ADD / UPDATE / 旧不覆新 / DELETE / 保护 ─────────────────────


def _import(db, upload, zip_path):
    return import_github_package(db, upload, zip_path)


def test_add_update_delete_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("BREADTH_DATA_PATH", "/nonexistent-breadth-data")
    r1 = _norm({"t": "情报甲", "d": "2026-09-28", "u": "https://v2/a", "b": "正文",
                "c": "半导体/设备", "sc": 7.0, "tg": "北方华创", "tp": "刻蚀", "aip": 1,
                "cl": "聚类X", "cp": [1, 2], "cln": "簇名", "dp": 3, "wr": "w1", "hb": 1,
                "cm": "应被剥离的私有评论", "fb": "私有反馈", "sr": "私有来源"})
    changes1 = [{"op": "ADD", "id": r1["id"], "key": f"情报甲|2026-09-28|https://v2/a", "v": 1}]
    db = SessionLocal()
    try:
        upload = _mk_upload(db, checksum=hashlib.sha256(b"zip-a").hexdigest())
        payload = _import(db, upload, _tmp_zip(tmp_path, _build_v2([r1], changes1)))
        assert payload["imported"] == 1 and payload["failed"] == 0, payload
        details = payload["details"]
        assert details["added"] == 1 and details["updated"] == 0

        rows = db.execute(text(
            "SELECT * FROM breadth_manual_records WHERE upload_id=:i"
        ), {"i": str(upload.id)}).mappings().all()
        assert len(rows) == 1
        row = rows[0]
        # 白名单剥离：私有字段不落地（五节）
        rj = row["record_json"]
        assert "cm" not in rj and "fb" not in rj and "sr" not in rj
        # 包往返不丢字段：公开字段全保留（验收 10）
        assert rj["cl"] == "聚类X" and rj["cp"] == [1, 2] and rj["cln"] == "簇名"
        assert rj["tg"] == "北方华创" and rj["tp"] == "刻蚀" and rj["aip"] == 1
        assert row["tag"] == "北方华创" and row["topic"] == "刻蚀" and row["ai_picked"] is True
        assert row["source_version"] == 1
        assert row["stable_id"] == r1["id"]

        # 索引任务已入队（upsert）
        tasks = db.execute(text(
            "SELECT op, status FROM breadth_index_tasks WHERE upload_id=:i"
        ), {"i": str(upload.id)}).mappings().all()
        assert len(tasks) == 1 and tasks[0]["op"] == "upsert" and tasks[0]["status"] == "pending"

        # ── UPDATE：重评分进增量（此前 t/b/i 哈希漏检的场景）──
        r1b = dict(r1)
        r1b["sc"] = 9.5
        r1b["aip"] = 1
        changes2 = [{"op": "UPDATE", "id": r1["id"], "key": "情报甲|2026-09-28|https://v2/a", "v": 2}]
        upload2 = _mk_upload(db, checksum=hashlib.sha256(b"zip-b").hexdigest())
        payload2 = _import(db, upload2, _tmp_zip(tmp_path, _build_v2([r1b], changes2, date="2026-09-29")))
        assert payload2["details"]["updated"] == 1 and payload2["details"]["added"] == 0
        row2 = db.execute(text(
            "SELECT score, source_version, upload_id, record_json FROM breadth_manual_records WHERE stable_id=:s"
        ), {"s": r1["id"]}).mappings().one()
        assert row2["score"] == "9.5" and row2["source_version"] == 2
        assert str(row2["upload_id"]) == str(upload2.id)  # 所有权移交最新包

        # ── 旧不覆新：v=1 的旧包不能再改回 ──
        r1c = dict(r1)
        r1c["sc"] = 1.0
        changes3 = [{"op": "UPDATE", "id": r1["id"], "key": "情报甲|2026-09-28|https://v2/a", "v": 1}]
        upload3 = _mk_upload(db, checksum=hashlib.sha256(b"zip-c").hexdigest())
        payload3 = _import(db, upload3, _tmp_zip(tmp_path, _build_v2([r1c], changes3, date="2026-09-27")))
        assert payload3["details"]["skipped_stale"] == 1
        assert db.execute(text(
            "SELECT score FROM breadth_manual_records WHERE stable_id=:s"
        ), {"s": r1["id"]}).scalar() == "9.5"

        # ── DELETE：行删除 + 索引删除任务；重放同一包 → deleted_missing 幂等 ──
        changes4 = [{"op": "DELETE", "id": r1["id"], "key": "情报甲|2026-09-28|https://v2/a", "v": 3}]
        upload4 = _mk_upload(db, checksum=hashlib.sha256(b"zip-d").hexdigest())
        payload4 = _import(db, upload4, _tmp_zip(tmp_path, _build_v2([], changes4, date="2026-09-30")))
        assert payload4["details"]["deleted"] == 1
        assert db.execute(text(
            "SELECT count(*) FROM breadth_manual_records WHERE stable_id=:s"
        ), {"s": r1["id"]}).scalar() == 0
        del_tasks = db.execute(text(
            "SELECT op FROM breadth_index_tasks WHERE upload_id=:i AND op='delete'"
        ), {"i": str(upload4.id)}).all()
        assert len(del_tasks) == 1
    finally:
        db.close()


def test_delete_protects_manual_rows(tmp_path, monkeypatch):
    """feed DELETE 不能误删人工/其他广度情报来源的同键记录。"""
    monkeypatch.setenv("BREADTH_DATA_PATH", "/nonexistent-breadth-data")
    db = SessionLocal()
    try:
        manual_upload = _mk_upload(db, section="breadth", source="other", title="manual.pdf")
        db.execute(text(
            "INSERT INTO breadth_manual_records "
            "(id, upload_id, user_id, title, document_date, url, level, intelligence_type, source_version) "
            "VALUES (:i, :u, 'feedv2-test', '同键记录', '2026-09-28', 'https://m/1', 0, 'news', 0)"
        ), {"i": str(uuid.uuid4()), "u": str(manual_upload.id)})
        db.commit()
        changes = [{"op": "DELETE", "id": "0" * 16, "key": "同键记录|2026-09-28|https://m/1", "v": 5}]
        upload = _mk_upload(db, checksum=hashlib.sha256(b"zip-e").hexdigest())
        payload = _import(db, upload, _tmp_zip(tmp_path, _build_v2([], changes)))
        assert payload["details"]["skipped_protected"] == 1
        assert db.execute(text(
            "SELECT count(*) FROM breadth_manual_records WHERE title='同键记录'"
        )).scalar() == 1
    finally:
        db.close()


def test_replay_repoints_rows(tmp_path, monkeypatch):
    """重复上传同一包：回放计数，且历史记录行挂到新上传（删除不再误删）。"""
    monkeypatch.setenv("BREADTH_DATA_PATH", "/nonexistent-breadth-data")
    r1 = _norm({"t": "重放目标", "d": "2026-09-28", "u": "https://v2/r"})
    changes = [{"op": "ADD", "id": r1["id"], "key": "重放目标|2026-09-28|https://v2/r", "v": 1}]
    data = _build_v2([r1], changes)
    db = SessionLocal()
    try:
        upload = _mk_upload(db, checksum=hashlib.sha256(data).hexdigest())
        payload = _import(db, upload, _tmp_zip(tmp_path, data))
        assert payload["imported"] == 1
        upload2 = _mk_upload(db, checksum=hashlib.sha256(data).hexdigest(), title="pkg2.zip")
        payload2 = _import(db, upload2, _tmp_zip(tmp_path, data, "pkg2.zip"))
        assert payload2["replayed"] is True
        rows = db.execute(text(
            "SELECT upload_id FROM breadth_manual_records WHERE title='重放目标'"
        )).all()
        assert len(rows) == 1 and str(rows[0][0]) == str(upload2.id)
    finally:
        db.close()


# ── 索引任务队列 ──────────────────────────────────────────────────────────


def test_queue_process_and_delete(monkeypatch, tmp_path):
    monkeypatch.setenv("BREADTH_DATA_PATH", "/nonexistent-breadth-data")
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://qa-test:0")
    calls: list[tuple[str, str]] = []

    def fake_upsert(payload):
        calls.append(("upsert", payload["document_id"]))
        assert payload["chunks"], "upsert 必须携带分块"
        return {"status": "ready", "chunk_count": len(payload["chunks"])}

    def fake_delete(document_id):
        calls.append(("delete", document_id))
        return {"status": "ok", "removed_chunks": 1}

    monkeypatch.setattr(bq, "_post_index_upsert", fake_upsert)
    monkeypatch.setattr(bq, "_post_index_delete", fake_delete)

    r1 = _norm({"t": "队列验证", "d": "2026-09-28", "u": "https://v2/q", "b": "正文" * 100})
    changes = [{"op": "ADD", "id": r1["id"], "key": "队列验证|2026-09-28|https://v2/q", "v": 1}]
    db = SessionLocal()
    try:
        upload = _mk_upload(db, checksum=hashlib.sha256(b"zip-q").hexdigest())
        _import(db, upload, _tmp_zip(tmp_path, _build_v2([r1], changes)))
        processed = bq.process_batch(db)
        assert processed == 1
        task = db.execute(text(
            "SELECT status, attempts FROM breadth_index_tasks WHERE upload_id=:i"
        ), {"i": str(upload.id)}).one()
        assert task[0] == "done" and task[1] == 1
        # 上传聚合状态：全部任务终结 → ready
        db.expire_all()
        status = db.execute(text(
            "SELECT embedding_status FROM uploaded_files WHERE id=:i"
        ), {"i": str(upload.id)}).scalar()
        assert status == "ready"

        # 删除任务
        from app.services.breadth_index_queue import enqueue_record_delete

        row_id = db.execute(text(
            "SELECT id FROM breadth_manual_records WHERE title='队列验证'"
        )).scalar()
        enqueue_record_delete(db, row_id, upload.id)
        db.commit()
        bq.process_batch(db)
        assert ("delete", str(row_id)) in calls
    finally:
        db.close()


def test_queue_retry_and_backoff(monkeypatch, tmp_path):
    """失败退避 → 恢复后重试成功；目标记录缺失 → 任务无害完成。"""
    monkeypatch.setenv("BREADTH_DATA_PATH", "/nonexistent-breadth-data")
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://qa-test:0")
    calls = {"n": 0}

    def failing_upsert(payload):
        calls["n"] += 1
        raise RuntimeError("qa down")

    monkeypatch.setattr(bq, "_post_index_upsert", failing_upsert)

    r1 = _norm({"t": "退避验证", "d": "2026-09-28", "u": "https://v2/b", "b": "正文"})
    changes = [{"op": "ADD", "id": r1["id"], "key": "退避验证|2026-09-28|https://v2/b", "v": 1}]
    db = SessionLocal()
    try:
        upload = _mk_upload(db, checksum=hashlib.sha256(b"zip-bk").hexdigest())
        _import(db, upload, _tmp_zip(tmp_path, _build_v2([r1], changes)))
        db.commit()
        processed = bq.process_batch(db)
        assert processed == 0 and calls["n"] == 1
        task = db.execute(text(
            "SELECT status, attempts, not_before FROM breadth_index_tasks WHERE upload_id=:i"
        ), {"i": str(upload.id)}).one()
        assert task[0] == "pending" and task[1] == 1 and task[2] is not None  # 退避等待

        # 服务恢复：清除退避（模拟时间流逝）后重试成功
        monkeypatch.setattr(bq, "_post_index_upsert", lambda payload: {"status": "ready"})
        db.execute(text(
            "UPDATE breadth_index_tasks SET not_before=NULL WHERE upload_id=:i"
        ), {"i": str(upload.id)})
        db.commit()
        assert bq.process_batch(db) == 1
        status = db.execute(text(
            "SELECT status FROM breadth_index_tasks WHERE upload_id=:i"
        ), {"i": str(upload.id)}).scalar()
        assert status == "done"

        # 目标记录缺失（已被删除）→ upsert 无害完成，不报错
        from app.services.breadth_index_queue import enqueue_record_upserts

        ghost = uuid.uuid4()
        enqueue_record_upserts(
            db, [type("Ghost", (), {"id": ghost, "upload_id": None})()]
        )
        db.commit()
        db.execute(text("DELETE FROM breadth_manual_records WHERE title='退避验证'"))
        db.commit()
        db.execute(text(
            "UPDATE breadth_index_tasks SET not_before=NULL, status='pending', attempts=0 "
            "WHERE target_key=:k"
        ), {"k": str(ghost)})
        db.commit()
        assert bq.process_batch(db) == 1  # 记录不在 → done
        db.execute(text("DELETE FROM breadth_index_tasks WHERE target_key=:k"), {"k": str(ghost)})
        db.commit()
    finally:
        db.close()


# ── 表格逐行模式 ──────────────────────────────────────────────────────────


def test_table_rows_csv_mapping_and_dedup(tmp_path, monkeypatch):
    from app.services.table_rows import import_rows, parse_table, validate_mapping

    csv_data = "标题,日期,链接,等级,正文\n情报一,2026-09-28,https://t/1,2,正文一\n情报一,2026-09-28,https://t/1,2,正文一\n,2026-09-28,,0,空标题\n情报二,,,,无日期行\n".encode("utf-8")
    sheets = parse_table(csv_data, "t.csv")
    assert sheets[0].headers == ["标题", "日期", "链接", "等级", "正文"]
    mapping = validate_mapping({"title": "标题", "date": "日期", "url": "链接", "level": "等级", "body": "正文"})
    db = SessionLocal()
    try:
        upload = _mk_upload(db, checksum=hashlib.sha256(b"csv-1").hexdigest())
        stats = import_rows(db, upload, sheets, mapping, fallback_date="2026-09-01", category_fallback=None)
        assert stats["rows_total"] == 4
        assert stats["imported"] == 2, stats      # 情报一/情报二（包内重复 1 条）
        assert stats["skipped_duplicate"] == 1
        assert stats["skipped_empty"] == 1        # 空标题
        db.flush()  # autoflush=False：显式刷出 pending 的记录行与索引任务
        rows = db.execute(text(
            "SELECT title, document_date, url, level, source_ref FROM breadth_manual_records "
            "WHERE upload_id=:i ORDER BY title"
        ), {"i": str(upload.id)}).mappings().all()
        assert len(rows) == 2
        by_title = {r["title"]: r for r in rows}
        assert by_title["情报一"]["level"] == 2
        assert by_title["情报二"]["document_date"] == "2026-09-01"  # 日期列缺失回退上传日期
        assert by_title["情报一"]["source_ref"]["row"] == 2        # 行号溯源（数据第2行）
        # 索引任务
        tasks = db.execute(text(
            "SELECT count(*) FROM breadth_index_tasks WHERE upload_id=:i"
        ), {"i": str(upload.id)}).scalar()
        assert tasks == 2
        # 再次导入同内容 → 全部去重（不重复入库）
        upload2 = _mk_upload(db, checksum=hashlib.sha256(b"csv-2").hexdigest())
        stats2 = import_rows(db, upload2, sheets, mapping, fallback_date="2026-09-01", category_fallback=None)
        assert stats2["imported"] == 0 and stats2["skipped_duplicate"] == 3
    finally:
        db.close()


def test_table_rows_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from app.services.table_rows import parse_table

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "情报"
    ws.append(["标题", "日期"])
    ws.append(["表行A", "2026-09-28"])
    ws.append([None, None])  # 空行跳过
    ws.append(["表行B", ""])
    buf = io.BytesIO()
    wb.save(buf)
    sheets = parse_table(buf.getvalue(), "t.xlsx")
    assert [s.name for s in sheets] == ["情报"]
    assert len(sheets[0].rows) == 2
    assert sheets[0].rows[0] == {"标题": "表行A", "日期": "2026-09-28"}


# ── note 文案 ─────────────────────────────────────────────────────────────


def test_note_with_details():
    payload = {
        "imported": 5, "skipped_upstream_conflict": 2, "failed": 1, "replayed": False,
        "details": {"updated": 3, "deleted": 1, "skipped_stale": 4, "gap_days": 3},
    }
    note = note_for_counts(payload)
    assert "导入 5 条" in note and "更新 3" in note and "删除 1" in note
    assert "旧版跳过 4" in note and "gap" not in note
    assert "--since-last" in note and "3 天" in note


def test_tombstone_rejects_stale_replay_and_conflict(tmp_path, monkeypatch):
    """墓碑（二.4，2026-09-30）：DELETE v3 后，乱序/补投递包重放
    ADD v2 拒绝复活；ADD v3 同内容幂等跳过；ADD v3 异内容判冲突；
    ADD v4 合法重新上架并清除墓碑。"""
    from app.models.feed_tombstone import FeedTombstone

    monkeypatch.setenv("BREADTH_DATA_PATH", "/nonexistent-breadth-data")
    r1 = _norm({
        "id": _stable_id("情报乙", "2026-09-28", "https://v2/b"),
        "t": "情报乙", "d": "2026-09-28", "u": "https://v2/b",
        "s": "源B", "c": "技术突破/芯片", "sc": 6.0, "i": 1,
        "b": "正文乙" * 10,
    })
    key = "情报乙|2026-09-28|https://v2/b"
    db = SessionLocal()
    try:
        # ① ADD v1
        upload1 = _mk_upload(db, checksum=hashlib.sha256(b"zip-t1").hexdigest())
        p1 = _import(db, upload1, _tmp_zip(
            tmp_path, _build_v2([r1], [{"op": "ADD", "id": r1["id"], "key": key, "v": 1}])))
        assert p1["details"]["added"] == 1

        # ② DELETE v3 → 墓碑持久化（版本 + 内容哈希）
        upload2 = _mk_upload(db, checksum=hashlib.sha256(b"zip-t2").hexdigest())
        p2 = _import(db, upload2, _tmp_zip(
            tmp_path, _build_v2([], [{"op": "DELETE", "id": r1["id"], "key": key, "v": 3}],
                                date="2026-09-30")))
        assert p2["details"]["deleted"] == 1
        tb = db.query(FeedTombstone).filter_by(feed_key_digest=gi._feed_key_digest_hex(key)).one()
        assert tb.deleted_version == 3 and tb.deleted_content_hash

        # ③ 乱序包重放 ADD v2 → 拒绝复活
        r_stale = dict(r1)
        r_stale["sc"] = 3.0
        upload3 = _mk_upload(db, checksum=hashlib.sha256(b"zip-t3").hexdigest())
        p3 = _import(db, upload3, _tmp_zip(
            tmp_path, _build_v2([r_stale], [{"op": "ADD", "id": r1["id"], "key": key, "v": 2}],
                                date="2026-09-29")))
        assert p3["details"]["skipped_tombstoned"] == 1 and p3["details"]["added"] == 0
        assert db.execute(text(
            "SELECT count(*) FROM breadth_manual_records WHERE stable_id=:s"
        ), {"s": r1["id"]}).scalar() == 0

        # ④ ADD v3 同内容 → 幂等跳过；④' ADD v3 异内容 → 冲突不落地
        r_same = dict(r1)
        upload4 = _mk_upload(db, checksum=hashlib.sha256(b"zip-t4").hexdigest())
        p4 = _import(db, upload4, _tmp_zip(
            tmp_path, _build_v2([r_same], [{"op": "ADD", "id": r1["id"], "key": key, "v": 3}],
                                date="2026-09-30")))
        assert p4["details"]["skipped_tombstoned"] == 1
        r_conf = dict(r1)
        r_conf["sc"] = 9.9
        upload5 = _mk_upload(db, checksum=hashlib.sha256(b"zip-t5").hexdigest())
        p5 = _import(db, upload5, _tmp_zip(
            tmp_path, _build_v2([r_conf], [{"op": "ADD", "id": r1["id"], "key": key, "v": 3}],
                                date="2026-09-30")))
        assert p5["details"]["conflicts"] == 1 and p5["details"]["added"] == 0
        assert p5["details"]["conflict_keys"] == [key]
        assert db.execute(text(
            "SELECT count(*) FROM breadth_manual_records WHERE stable_id=:s"
        ), {"s": r1["id"]}).scalar() == 0

        # ⑤ ADD v4 → 合法重新上架，墓碑清除
        r_new = dict(r1)
        r_new["sc"] = 8.0
        upload6 = _mk_upload(db, checksum=hashlib.sha256(b"zip-t6").hexdigest())
        p6 = _import(db, upload6, _tmp_zip(
            tmp_path, _build_v2([r_new], [{"op": "ADD", "id": r1["id"], "key": key, "v": 4}],
                                date="2026-10-01")))
        assert p6["details"]["added"] == 1
        assert db.query(FeedTombstone).filter_by(
            feed_key_digest=gi._feed_key_digest_hex(key)).count() == 0
        assert db.execute(text(
            "SELECT source_version FROM breadth_manual_records WHERE stable_id=:s"
        ), {"s": r1["id"]}).scalar() == 4

        # ⑥ DELETE v2（低于行内版本 4）→ skipped_stale；再 DELETE v5 → 墓碑推进到 5
        upload7 = _mk_upload(db, checksum=hashlib.sha256(b"zip-t7").hexdigest())
        p7 = _import(db, upload7, _tmp_zip(
            tmp_path, _build_v2([], [{"op": "DELETE", "id": r1["id"], "key": key, "v": 2}],
                                date="2026-10-01")))
        assert p7["details"]["skipped_stale"] == 1
        upload8 = _mk_upload(db, checksum=hashlib.sha256(b"zip-t8").hexdigest())
        p8 = _import(db, upload8, _tmp_zip(
            tmp_path, _build_v2([], [{"op": "DELETE", "id": r1["id"], "key": key, "v": 5}],
                                date="2026-10-02")))
        assert p8["details"]["deleted"] == 1
        assert db.query(FeedTombstone).filter_by(
            feed_key_digest=gi._feed_key_digest_hex(key)).one().deleted_version == 5
    finally:
        db.close()

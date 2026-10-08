#!/usr/bin/env python3
"""历史表格类型修复：默认只读；执行必须指定单个上传和新的持久备份。

  python scripts/repair_row_intelligence_types.py --upload-id UUID
  python scripts/repair_row_intelligence_types.py --execute --upload-id UUID --backup /safe/new.json

退出码：0=只读检查无待人工项/执行无变化；2=参数或待人工问题；
3=已提交并入队，尚未验证异步索引（绝不宣称三路已修复）。
备份 prepared 表示事务提交结果可能未知，恢复时必须核对数据库，不可盲目重放。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.uploaded_file import UploadedFile
from app.services.table_rows import (
    TYPE_COLUMN_EXACT, TYPE_VALUES, compute_content_hash_v2, normalize_date_cell,
    parse_table, strip_type_ws,
)

SNAPSHOT_FIELDS = (
    "title", "document_date", "url", "body", "ai_summary", "intelligence_type",
    "content_hash", "source_version", "source_ref", "origin_section", "category",
    "record_json", "stable_id", "feed_key_digest", "updated_at",
)


def _snapshot(rec):
    # JSON copy avoids sharing SQLAlchemy mutable values with a later mutation.
    return json.loads(json.dumps({k: getattr(rec, k) for k in SNAPSHOT_FIELDS}, default=str))


def _norm(value):
    return str(value or "").strip()


def _resolve_type(headers, row):
    hits = [h for h in headers if strip_type_ws(str(h)) in TYPE_COLUMN_EXACT]
    if len(hits) != 1:
        return None, "情报类型列缺失或不唯一"
    raw = strip_type_ws(str(row.get(hits[0]) or ""))
    return TYPE_VALUES.get(raw), raw


def _row_identity_matches(row, headers, rec):
    def col(*aliases):
        hits = [h for h in headers if strip_type_ws(str(h)) in aliases]
        return row.get(hits[0]) if len(hits) == 1 else None
    title = col("标题", "题目", "title", "名称")
    if title is None or _norm(title) != _norm(rec.title):
        return False
    date = col("日期", "date", "时间")
    if date is not None:
        normalized = normalize_date_cell(date)
        if (_norm(date) and not normalized) or normalized != _norm(rec.document_date):
            return False
    url = col("链接", "网址", "url")
    return url is None or _norm(url) == _norm(rec.url)


def _iter_sheet_rows(path):
    for sheet in parse_table(path.read_bytes(), path.name):
        yield sheet.name, list(sheet.headers), {
            int(sheet.row_nos[i] if i < len(sheet.row_nos) else i + 2): row
            for i, row in enumerate(sheet.rows)
        }


def _resolve_row(path, rec):
    """Physical/legacy ordinal hints never override a unique normalized identity."""
    ref = rec.source_ref or {}
    for sheet, headers, rows in _iter_sheet_rows(path):
        if sheet != ref.get("sheet"):
            continue
        matches = [(n, row) for n, row in rows.items() if _row_identity_matches(row, headers, rec)]
        if len(matches) != 1:
            raise ValueError("行身份不一致或不唯一（标题/规范化日期/链接），需人工核对")
        number, row = matches[0]
        new_type, raw = _resolve_type(headers, row)
        if new_type is None:
            raise ValueError(f"类型列值无法映射：{raw!r}")
        return number, new_type, raw
    raise ValueError(f"工作表 {ref.get('sheet')!r} 不在原文件")


def _source_path(db, rec):
    upload = db.get(UploadedFile, rec.upload_id)
    if (not upload or upload.primary_section != "breadth" or upload.breadth_source != "other"
            or rec.origin_section not in (None, "breadth")):
        raise ValueError("来源冲突：仅修复其他广度情报，行业/ATSC/GitHub 不自动改型")
    from app.services.upload_ingestion import safe_upload_path
    path = safe_upload_path(upload.stored_filename)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if not upload.checksum_sha256 or digest != upload.checksum_sha256:
        raise ValueError("原文件校验和缺失或不一致，需人工确认")
    return path, digest


def _save_backup(path, payload, *, create=False):
    """Exclusive first creation; atomic subsequent writes, fsync before any DB write."""
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if create:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        fd, temp = tempfile.mkstemp(prefix=".type-backup-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    if json.loads(path.read_text(encoding="utf-8")) != payload:
        raise OSError("备份回读不一致，停止执行")


def verify_backup(path, upload_id):
    """Read-only, per-record DB + worker + canonical convergence check."""
    from app.models.index_task import IndexTask
    from app.services.index_status import canonical_document_status
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("upload_id") != str(upload_id):
        raise ValueError("备份与 --upload-id 不匹配")
    entries = payload.get("entries") or []
    if not entries or not all(e.get("executed") for e in entries):
        print("备份为空或存在未确认执行项，不能宣称修复通过")
        return 2
    docs = canonical_document_status([e["record_id"] for e in entries]) or {}
    complete = True
    with SessionLocal() as db:
        for e in entries:
            rec = db.get(BreadthManualRecord, uuid.UUID(e["record_id"]))
            doc = docs.get(e["record_id"], {})
            tasks = list(db.scalars(select(IndexTask).where(IndexTask.target_key == e["record_id"])))
            chunks = doc.get("chunks", 0)
            ok = bool(rec and rec.upload_id == upload_id and rec.origin_section in (None, "breadth")
                and rec.intelligence_type == e["new_type"] and rec.content_hash == e["new_content_hash"]
                and rec.source_version == e["new_source_version"]
                and tasks and all(t.status == "done" for t in tasks)
                and chunks > 0 and doc.get("live_chunks") == chunks
                and doc.get("primary_sections") == ["breadth"]
                and doc.get("content_shas") == [e["new_content_hash"]]
                and doc.get("content_sha_rows") == chunks
                and doc.get("intelligence_types") == [e["new_type"]]
                and doc.get("intelligence_type_rows") == chunks
                and doc.get("source_versions") == [str(e["new_source_version"])]
                and doc.get("source_version_rows") == chunks
                and all(doc.get(route) is True for route in ("vector_ok", "bm25_ok", "graph_ok")))
            print(json.dumps({"record_id": e["record_id"], "verified": ok,
                              "expected_type": e["new_type"], "index": doc}, ensure_ascii=False))
            complete = complete and ok
    return 0 if complete else 3


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--verify-only", action="store_true", help="只读核对备份中每条记录的队列与三路索引类型/版本")
    ap.add_argument("--backup", default="")
    ap.add_argument("--upload-id", default="")
    args = ap.parse_args(argv)
    if (args.execute or args.verify_only) and (not args.backup or not args.upload_id):
        ap.error("--execute 必须同时指定 --upload-id 和新的 --backup 文件")
    try:
        upload_id = uuid.UUID(args.upload_id) if args.upload_id else None
    except ValueError:
        ap.error("--upload-id 不是合法 UUID")
    if args.verify_only:
        return verify_backup(Path(args.backup), upload_id)
    plan, pending = [], []
    with SessionLocal() as db:
        stmt = select(BreadthManualRecord).where(BreadthManualRecord.source_ref.isnot(None))
        if upload_id:
            stmt = stmt.where(BreadthManualRecord.upload_id == upload_id)
        candidates = [r for r in db.scalars(stmt) if isinstance(r.source_ref, dict) and r.source_ref.get("sheet")]
        for rec in candidates:
            entry = {"record_id": str(rec.id), "upload_id": str(rec.upload_id),
                     "source_ref": rec.source_ref, "old_type": rec.intelligence_type,
                     "before": _snapshot(rec), "executed": False, "state": "planned"}
            try:
                path, digest = _source_path(db, rec)
                number, new_type, raw = _resolve_row(path, rec)
                if new_type == rec.intelligence_type:
                    continue
                entry.update(new_type=new_type, raw_value=raw, row=number,
                             sheet=rec.source_ref["sheet"], file_sha256=digest,
                             row_resolution="physical" if str(number) == str(rec.source_ref.get("row")) else "unique_identity_legacy_hint")
                plan.append(entry)
            except (ValueError, OSError) as exc:
                entry["reason"] = str(exc)
                pending.append(entry)
    print(f"候选（逐行表格存量记录）：{len(candidates)}")
    print(f"可修复：{len(plan)} · 待人工（不猜测）：{len(pending)}")
    for e in plan:
        print(f"  [fix] {e['record_id']} #{e['row']} {e['old_type']!r} -> {e['new_type']}（原值 {e['raw_value']!r}）")
    for e in pending:
        print(f"  [pending] {e['record_id']} {e['reason']}")
    if not args.execute or not plan:
        return 2 if pending else 0

    backup = Path(args.backup).resolve()
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(),
               "upload_id": str(upload_id), "entries": plan, "pending": pending,
               "executed": 0, "index_verification": "not_verified"}
    _save_backup(backup, payload, create=True)
    from app.services.breadth_index_queue import enqueue_record_upserts
    for entry in plan:
        with SessionLocal() as db:
            try:
                # Lock upload + record: deletion, source changes and record updates cannot race us.
                db.scalar(select(UploadedFile).where(UploadedFile.id == upload_id).with_for_update())
                rec = db.scalar(select(BreadthManualRecord).where(
                    BreadthManualRecord.id == uuid.UUID(entry["record_id"])).with_for_update())
                if rec is None or _snapshot(rec) != entry["before"]:
                    raise ValueError("记录已删除或规划后发生并发修改")
                path, digest = _source_path(db, rec)
                number, new_type, raw = _resolve_row(path, rec)
                if (digest, number, new_type) != (entry["file_sha256"], entry["row"], entry["new_type"]):
                    raise ValueError("执行期原文件/行身份/类型发生变化")
                new_hash = compute_content_hash_v2(rec.title or "", rec.document_date or "", rec.url or "",
                                                   rec.body or "", rec.ai_summary or "", new_type)
                entry.update(actual_old_type=rec.intelligence_type, old_content_hash=rec.content_hash,
                             new_content_hash=new_hash, old_source_version=rec.source_version,
                             new_source_version=(rec.source_version or 0) + 1, state="prepared")
                # Actual before-image and intended after-image durable BEFORE UPDATE/queue/COMMIT.
                _save_backup(backup, payload)
                rec.intelligence_type = new_type
                rec.content_hash = new_hash
                rec.source_version = entry["new_source_version"]
                enqueue_record_upserts(db, [rec])
                db.commit()
            except Exception as exc:
                db.rollback()
                entry.update(state="not_confirmed", error=str(exc))
                _save_backup(backup, payload)
                continue
        entry.update(executed=True, state="committed_queued")
        payload["executed"] += 1
        _save_backup(backup, payload)
    print(f"数据库已修复并入队：{payload['executed']}；异步三路索引尚未验收")
    return 3 if payload["executed"] else 2


if __name__ == "__main__":
    sys.exit(main())

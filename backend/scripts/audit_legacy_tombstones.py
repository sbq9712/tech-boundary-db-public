#!/usr/bin/env python3
"""Read-only audit of legacy unscoped tombstones. Never unblocks any identity.

Run against an explicitly supplied record-ops JSON snapshot from canonical.
Potential collisions are evidence for review, not proof that a deletion was wrong.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.index_task import IndexTask
from app.services.breadth_index_queue import canonical_record_key_sha


def audit(state, records, tasks):
    tombstones = state.get("tombstones")
    if not isinstance(tombstones, dict):
        raise ValueError("状态快照缺少 tombstones 对象")
    evidence = {}
    for rec in records:
        legacy = canonical_record_key_sha(rec.title, rec.document_date or "", rec.url or "", origin_section="breadth")
        if legacy in tombstones:
            evidence.setdefault(legacy, {"records": [], "old_tasks": []})["records"].append({
                "record_id": str(rec.id), "upload_id": str(rec.upload_id),
                "origin_section": rec.origin_section, "title": rec.title,
                "content_hash": rec.content_hash, "source_version": rec.source_version})
    for task in tasks:
        key = (task.payload or {}).get("record_key_sha_legacy")
        if key and key in tombstones:
            evidence.setdefault(key, {"records": [], "old_tasks": []})["old_tasks"].append({
                "task_id": str(task.id), "target_key": task.target_key, "status": task.status})
    return {"read_only": True, "tombstones_total": len(tombstones),
            "unattributed_tombstones": sorted(set(tombstones) - set(evidence)),
            "pending_review": [{"legacy_key": key, "tombstone": tombstones[key],
                                "reason": "不能从存活行/旧队列证明删除意图，禁止自动解除", **value}
                               for key, value in sorted(evidence.items())]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-json", type=Path, required=True)
    args = parser.parse_args()
    state = json.loads(args.state_json.read_text())
    with SessionLocal() as db:
        # Explicitly read-only at the database transaction boundary.
        from sqlalchemy import text
        db.execute(text("SET TRANSACTION READ ONLY"))
        result = audit(state, db.scalars(select(BreadthManualRecord)).all(),
                       db.scalars(select(IndexTask)).all())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["pending_review"] or result["unattributed_tombstones"] else 0


if __name__ == "__main__":
    sys.exit(main())

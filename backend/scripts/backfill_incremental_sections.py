#!/usr/bin/env python3
"""任务二 2.1：存量增量索引归属回填（幂等，可重放）。

前提：alembic 0033 已把 breadth_manual_records.origin_section 按 FK 回填。
本脚本把 DB 侧归属写进 canonical-qa 增量索引的 chunk_metadata（不重嵌入、
不重分词），用于：
- 队列启用前已入库的历史 GitHub/表格记录；
- Docling 上传链（request_incremental_index 注入 primary_section 部署前）
  的历史文档。

输出：可追溯回填计数 + canonical 侧无归属文档清单（不猜测——上传记录
已删除的文档保持无归属，由 /api/index/status.unattributed_document_ids
单独列出）。

用法（api 容器内或同网主机）：
  python scripts/backfill_incremental_sections.py            # 执行回填
  python scripts/backfill_incremental_sections.py --dry-run  # 只列计划
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.breadth_manual_record import BreadthManualRecord  # noqa: E402
from app.models.uploaded_file import UploadedFile  # noqa: E402

VALID = ("breadth", "industry", "atsc")


def _qa_base() -> str:
    base = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    if not base:
        raise SystemExit("TECHDB_QA_SERVICE_URL 未配置")
    return base


def _headers() -> dict:
    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    return {"X-TechDB-Index-Token": token} if token else {}


def _fetch_status(client: httpx.Client) -> dict:
    r = client.get(f"{_qa_base()}/api/index/status", headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()


def _iter_record_attributions(db) -> Iterable[tuple[str, str]]:
    """(document_id, origin_section)：行记录表（含 GitHub 包/表格逐行）。"""
    rows = db.execute(
        select(
            BreadthManualRecord.id,
            BreadthManualRecord.origin_section,
            UploadedFile.primary_section,
        ).join(UploadedFile, BreadthManualRecord.upload_id == UploadedFile.id)
    ).all()
    for rid, origin, upload_section in rows:
        section = (origin or upload_section or "").strip().lower()
        if section not in VALID:
            continue
        yield str(rid), section


def _iter_document_attributions(db) -> Iterable[tuple[str, str]]:
    """(document_id, primary_section)：Docling 文档上传（一文档一记录）。"""
    rows = db.execute(
        select(UploadedFile.id, UploadedFile.primary_section)
    ).all()
    for uid, section in rows:
        section = (section or "").strip().lower()
        if section not in VALID:
            continue
        yield str(uid), section


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    plan: dict[str, str] = {}
    try:
        for did, section in _iter_record_attributions(db):
            plan[did] = section
        for did, section in _iter_document_attributions(db):
            plan.setdefault(did, section)
    finally:
        db.close()

    with httpx.Client() as client:
        status = _fetch_status(client)
        docs = status.get("documents", {})
        todo = {
            did: section for did, section in plan.items()
            if docs.get(did, {}).get("primary_section") != section
        }
        unattributed = list(status.get("unattributed_document_ids") or [])
        print(f"增量索引文档 {len(docs)} · DB 可追溯 {len(plan)} · 待回填 {len(todo)}")
        print(f"canonical 无归属文档 {len(unattributed)}（不猜测；DB 已删记录的残留）")
        if args.dry_run:
            for did, section in sorted(todo.items()):
                print(f"  [dry-run] {did} -> {section}")
            return
        ok = miss = err = 0
        for did, section in sorted(todo.items()):
            try:
                r = client.post(
                    f"{_qa_base()}/api/index/metadata-patch",
                    headers=_headers(),
                    json={"document_id": did, "primary_section": section},
                    timeout=60,
                )
                if r.status_code == 200:
                    ok += 1
                elif r.status_code == 404:
                    miss += 1
                else:
                    err += 1
                    print(f"  ! {did} -> {section}: HTTP {r.status_code}")
            except httpx.HTTPError as exc:
                err += 1
                print(f"  ! {did}: {exc}")
        print(f"回填完成：ok={ok} 不在索引(幂等跳过)={miss} 失败={err}")
        if err:
            raise SystemExit(1)
        final = _fetch_status(client)
        left = list(final.get("unattributed_document_ids") or [])
        print(f"回填后无归属文档 {len(left)}" + (f"：{left[:10]}" if left else ""))


if __name__ == "__main__":
    main()

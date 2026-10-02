#!/usr/bin/env python3
"""任务三 3.4：逐行表格「情报类型」历史修复（dry-run/backup/幂等）。

背景：类型严格化（3.1-3.3）之前导入的「其他广度情报」行记录可能缺
intelligence_type 或值不在 {news, literature}。本脚本按 source_ref
（原文件/工作表/物理行号）回读原上传文件，用「情报类型」列的原始值
重新判定类型：

- 只修「能对上的」：原文件可读 + 行身份（标题/日期/URL）与记录一致 +
  类型列值合法映射——三者齐备才 UPDATE；
- 对不上的（文件缺失/身份漂移/值仍非法）输出 pending 清单，不猜测；
- --dry-run 只打印计划；--backup PATH 先落 JSON 备份再改；
- UPDATE 后重入队索引任务（chunk_metadata.intelligence_type 同步）；
  幂等：重复执行时已合法记录为 no-op。

用法（api 容器内或同网主机）：
  python scripts/repair_row_intelligence_types.py --dry-run
  python scripts/repair_row_intelligence_types.py --backup /tmp/type-backup.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.breadth_manual_record import BreadthManualRecord  # noqa: E402
from app.models.uploaded_file import UploadedFile  # noqa: E402
from app.services.table_rows import (  # noqa: E402
    TYPE_COLUMN_EXACT,
    TYPE_VALUES,
    parse_table,
    strip_type_ws,
)

VALID_TYPES = set(TYPE_VALUES.values())


def _norm(s: object) -> str:
    return str(s or "").strip()


def _resolve_type(headers: list[str], row: dict) -> tuple[str | None, str]:
    """从原文件行解析类型：精确列名 + 值映射（与导入严格口径一致）。"""
    hit = next(
        (h for h in headers if strip_type_ws(str(h)) in TYPE_COLUMN_EXACT), None
    )
    if hit is None:
        return None, "原文件无「情报类型」列"
    raw = strip_type_ws(str(row.get(hit) or ""))
    return TYPE_VALUES.get(raw), raw


def _row_identity_matches(row: dict, headers: list[str], rec: BreadthManualRecord) -> bool:
    """身份核对：标题必配；日期/URL 列存在时值必须一致（空对空）。"""
    def col(*aliases) -> str | None:
        for a in aliases:
            for h in headers:
                if strip_type_ws(str(h)) == a:
                    return str(row.get(h) or "").strip()
        return None

    title = col("标题", "题目", "title", "名称")
    if title is None or _norm(title) != _norm(rec.title):
        return False
    date = col("日期", "date", "时间")
    if date is not None and _norm(date) != _norm(rec.document_date):
        return False
    url = col("链接", "网址", "url")
    if url is not None and _norm(url) != _norm(rec.url):
        return False
    return True


def _iter_sheet_rows(path: Path):
    """解析原文件：yield (sheet_name, headers, {物理行号: row_dict})。"""
    data = path.read_bytes()
    sheets = parse_table(data, path.name)
    for sheet in sheets:
        headers = list(sheet.headers)
        row_map: dict[int, dict] = {}
        for idx, row in enumerate(sheet.rows):
            row_no = sheet.row_nos[idx] if idx < len(sheet.row_nos) else idx + 2
            row_map[int(row_no)] = row
        yield sheet.name, headers, row_map


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", type=str, default="")
    args = ap.parse_args()

    db = SessionLocal()
    plan: list[dict] = []
    pending: list[dict] = []
    try:
        # 候选：source_ref 含 sheet（逐行表格导入）的全部记录——类型列
        # NOT NULL（默认 'news'），存量问题既可能是非法值，也可能是被
        # 默认值顶替的错误标型（文件里是「文献」但库里是 news）。
        # 统一口径：回读原文件重算，与库值不同即列入修复计划。
        rows = db.scalars(
            select(BreadthManualRecord).where(
                BreadthManualRecord.source_ref.isnot(None),
            )
        ).all()
        candidates = [
            r for r in rows
            if isinstance(r.source_ref, dict) and r.source_ref.get("sheet")
        ]
        upload_cache: dict[uuid.UUID, Path | None] = {}
        for rec in candidates:
            entry = {
                "record_id": str(rec.id),
                "upload_id": str(rec.upload_id) if rec.upload_id else None,
                "source_ref": rec.source_ref,
                "old_type": rec.intelligence_type,
            }
            upath: Path | None = None
            if rec.upload_id in upload_cache:
                upath = upload_cache[rec.upload_id]
            else:
                upload = db.get(UploadedFile, rec.upload_id) if rec.upload_id else None
                if upload and upload.stored_filename:
                    from app.services.upload_ingestion import safe_upload_path

                    p = safe_upload_path(upload.stored_filename)
                    upath = p if p.exists() else None
                else:
                    upath = None
                upload_cache[rec.upload_id] = upath
            if upath is None:
                entry["reason"] = "原上传文件不可读（已删除或存储缺失）"
                pending.append(entry)
                continue
            ref = rec.source_ref or {}
            target_row = int(ref.get("row") or 0)
            found = False
            for sheet_name, headers, row_map in _iter_sheet_rows(upath):
                if sheet_name != ref.get("sheet"):
                    continue
                found = True
                row = row_map.get(target_row)
                if row is None:
                    entry["reason"] = f"物理行 {target_row} 不在原文件（文件可能已更新）"
                    pending.append(entry)
                    break
                if not _row_identity_matches(row, headers, rec):
                    entry["reason"] = "行身份不一致（标题/日期/链接与记录不匹配）"
                    pending.append(entry)
                    break
                new_type, raw = _resolve_type(headers, row)
                if new_type is None:
                    entry["reason"] = f"类型列值无法映射：{raw!r}"
                    pending.append(entry)
                    break
                if new_type == (rec.intelligence_type or ""):
                    entry["reason"] = f"库值已一致（{new_type}），无需修复"
                    # 不进 plan 也不进 pending——幂等 no-op
                    break
                entry.update({
                    "new_type": new_type,
                    "raw_value": raw,
                    "sheet": sheet_name,
                    "row": target_row,
                })
                plan.append(entry)
                break
            if not found:
                entry["reason"] = f"工作表 {ref.get('sheet')!r} 不在原文件"
                pending.append(entry)
    finally:
        db.close()

    print(f"候选（逐行表格存量记录）：{len(candidates)}")
    print(f"可修复：{len(plan)} · 待人工（不猜测）：{len(pending)}")
    for e in plan:
        print(f"  [fix] {e['record_id'][:8]} {e['source_ref'].get('file')}#{e['row']} "
              f"{e['old_type']!r} -> {e['new_type']}（原值 {e['raw_value']!r}）")
    for e in pending:
        print(f"  [pending] {e['record_id'][:8]} {e['reason']}")

    if args.dry_run or not plan:
        return

    if args.backup:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "entries": plan,
        }
        Path(args.backup).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"备份写入 {args.backup}")

    # 幂等执行：UPDATE + 重入队
    db = SessionLocal()
    fixed = 0
    try:
        from app.services.breadth_index_queue import enqueue_record_upserts

        for e in plan:
            rec = db.get(BreadthManualRecord, uuid.UUID(e["record_id"]))
            if rec is None or (rec.intelligence_type or "") in VALID_TYPES:
                continue  # 已被并发修复——幂等跳过
            rec.intelligence_type = e["new_type"]
            db.commit()
            enqueue_record_upserts(db, [rec])
            fixed += 1
        db.commit()
    finally:
        db.close()
    print(f"修复完成：{fixed} 条已 UPDATE 并重入队（其余见 pending 清单）")


if __name__ == "__main__":
    main()

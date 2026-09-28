"""表格逐行导入（六节）：Excel/CSV 每行一个情报，不要求文件级日期。

- 逐行模式：openpyxl（xlsx）/csv 模块（自动识别 UTF-8/GBK 编码）按单元格
  读取真实表格行——绝不拿 Docling 文档切块冒充行数据；
- 列映射/预览：row-preview 返回工作表名、表头与前 N 行，前端映射后回传；
- 溯源：每条记录的 source_ref 记录 原文件/工作表/行号；
- 空标题行跳过；日期列可选（缺失回退上传日期）。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import select

logger = logging.getLogger(__name__)

PREVIEW_ROWS = 20
MAX_ROWS = 20_000
ALLOWED_SUFFIXES = {".xlsx", ".csv"}


class TableParseError(ValueError):
    """表格解析失败/格式不合规。"""


@dataclass(slots=True)
class TableSheet:
    name: str
    headers: list[str]
    rows: list[dict] = field(default_factory=list)  # 全量行（预览时只取前 N）


def _decode_csv(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise TableParseError("无法识别 CSV 编码（请使用 UTF-8 或 GBK）")


def parse_csv(data: bytes) -> list[TableSheet]:
    text = _decode_csv(data)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise TableParseError("CSV 文件为空")
    headers = [str(h or "").strip() for h in rows[0]]
    if not any(headers):
        raise TableParseError("CSV 首行没有可用表头")
    sheet = TableSheet(name="csv", headers=headers)
    for line_no, raw in enumerate(rows[1:], start=2):
        if not any(str(c or "").strip() for c in raw):
            continue  # 整行为空：跳过
        row = {}
        for i, header in enumerate(headers):
            if header:
                row[header] = str(raw[i]).strip() if i < len(raw) else ""
        sheet.rows.append(row)
        if len(sheet.rows) >= MAX_ROWS:
            break
    return [sheet]


def parse_xlsx(data: bytes) -> list[TableSheet]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise TableParseError("服务器缺少 openpyxl，无法解析 Excel") from exc
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise TableParseError(f"Excel 解析失败：{exc}") from exc
    sheets: list[TableSheet] = []
    try:
        for ws in wb.worksheets:
            sheet = TableSheet(name=ws.title or f"sheet{len(sheets) + 1}", headers=[])
            header_row = None
            for row in ws.iter_rows(values_only=True):
                values = ["" if v is None else str(v).strip() for v in row]
                if header_row is None:
                    if any(values):
                        sheet.headers = values
                        header_row = True
                    continue
                if not any(values):
                    continue
                row_dict: dict[str, str] = {}
                for i, header in enumerate(sheet.headers):
                    if header:
                        row_dict[header] = values[i] if i < len(values) else ""
                sheet.rows.append(row_dict)
                if len(sheet.rows) >= MAX_ROWS:
                    break
            if header_row is not None and any(sheet.headers):
                sheets.append(sheet)
    finally:
        wb.close()
    if not sheets:
        raise TableParseError("Excel 中没有带表头的工作表")
    return sheets


def parse_table(data: bytes, filename: str, sheet_name: str | None = None) -> list[TableSheet]:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == ".csv":
        return parse_csv(data)
    if suffix == ".xlsx":
        sheets = parse_xlsx(data)
        if sheet_name:
            matched = [s for s in sheets if s.name == sheet_name]
            if not matched:
                raise TableParseError(f"工作表不存在：{sheet_name}")
            return matched
        return sheets
    raise TableParseError("逐行模式只支持 .xlsx / .csv")


def preview(data: bytes, filename: str, sheet_name: str | None = None) -> dict:
    sheets = parse_table(data, filename, sheet_name)
    return {
        "sheets": [
            {
                "name": s.name,
                "headers": s.headers,
                "total_rows": len(s.rows),
                "rows": s.rows[:PREVIEW_ROWS],
            }
            for s in sheets
        ]
    }


# 列映射允许的语义槽位（title 必填，其余可选）
MAPPING_SLOTS = ("title", "date", "category", "url", "source", "level", "body", "summary")


def validate_mapping(mapping: object) -> dict[str, str]:
    if not isinstance(mapping, dict):
        raise TableParseError("column_mapping 必须是对象")
    cleaned: dict[str, str] = {}
    for slot in MAPPING_SLOTS:
        col = mapping.get(slot)
        if col is None:
            continue
        col = str(col).strip()
        if col:
            cleaned[slot] = col
    if "title" not in cleaned:
        raise TableParseError("column_mapping 必须映射 title 列")
    return cleaned


# ── 行 → 广度记录（逐行入库 + 问答索引入队） ──────────────────────────────


def row_to_record_fields(
    row: dict[str, str],
    mapping: dict[str, str],
    *,
    upload_id,
    user_id: str,
    fallback_date: str | None,
    category_fallback: str | None,
    source_file: str,
    sheet_name: str,
    row_no: int,
) -> dict | None:
    """一行 → BreadthManualRecord 字段。空标题返回 None（调用方跳过计数）。

    每条记录带 source_ref（原文件/工作表/行号）满足溯源要求；日期列缺失时
    回退上传日期（不要求文件级日期）。
    """
    title = str(row.get(mapping["title"], "") or "").strip()
    if not title:
        return None
    date = ""
    if "date" in mapping:
        date = str(row.get(mapping["date"], "") or "").strip()
    if not date and fallback_date:
        date = str(fallback_date)
    url = str(row.get(mapping.get("url", ""), "") or "").strip() if "url" in mapping else ""
    body = str(row.get(mapping.get("body", ""), "") or "").strip() if "body" in mapping else ""
    summary = str(row.get(mapping.get("summary", ""), "") or "").strip() if "summary" in mapping else ""
    category = (
        str(row.get(mapping.get("category", ""), "") or "").strip()
        if "category" in mapping else ""
    ) or category_fallback or ""
    level = 0
    if "level" in mapping:
        raw = str(row.get(mapping["level"], "") or "").strip()
        try:
            level = max(0, min(3, int(float(raw))))
        except ValueError:
            level = 0

    content_hash = hashlib.sha256(
        json.dumps(
            {"t": title, "d": date, "u": url, "b": body, "s": summary},
            ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return dict(
        upload_id=upload_id,
        user_id=user_id,
        title=title[:500],
        body=(body or summary)[:20000] or None,
        category=category[:500] or None,
        document_date=date[:32] or None,
        level=level,
        intelligence_type="news",
        source_name=str(row.get(mapping.get("source", ""), "") or "").strip()[:255]
        or source_file[:255],
        url=url[:1024] or None,
        key_parameters=[],
        ai_summary=summary[:20000] or None,
        source_version=1,
        content_hash=content_hash,
        source_ref={"file": source_file, "sheet": sheet_name, "row": row_no},
    )


def import_rows(
    db,
    record,
    sheets: list[TableSheet],
    mapping: dict[str, str],
    *,
    fallback_date: str | None,
    category_fallback: str | None,
) -> dict:
    """逐行入库：去重（包内 + 撞库）→ breadth_manual_records + 索引任务。

    不重复入库：同内容哈希的行（包内重复或库内已存在）跳过并计数。"""
    from app.models.breadth_manual_record import BreadthManualRecord
    from app.services.breadth_index_queue import enqueue_record_upserts

    existing_hashes = set(
        db.scalars(select(BreadthManualRecord.content_hash)).all()
    )
    seen_hashes: set[str] = set()
    created: list[BreadthManualRecord] = []
    skipped_empty = skipped_duplicate = 0
    row_no = 1
    for sheet in sheets:
        for row in sheet.rows:
            row_no += 1
            fields = row_to_record_fields(
                row, mapping,
                upload_id=record.id, user_id=record.submitted_by,
                fallback_date=fallback_date, category_fallback=category_fallback,
                source_file=record.original_filename, sheet_name=sheet.name, row_no=row_no,
            )
            if fields is None:
                skipped_empty += 1
                continue
            digest = fields["content_hash"]
            if digest in seen_hashes or digest in existing_hashes:
                skipped_duplicate += 1
                continue
            seen_hashes.add(digest)
            created.append(BreadthManualRecord(**fields))
    db.add_all(created)
    db.flush()
    if created:
        enqueue_record_upserts(db, created)
    return {
        "rows_total": sum(len(s.rows) for s in sheets),
        "imported": len(created),
        "skipped_empty": skipped_empty,
        "skipped_duplicate": skipped_duplicate,
    }

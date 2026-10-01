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
import datetime
import json
import logging
import re
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

# Excel 日期序列号合理范围（1900-01-01 起）：1990-01-01 ≈ 32874，2079 ≈ 65380
_EXCEL_EPOCH = datetime.date(1899, 12, 30)
_EXCEL_SERIAL_MIN, _EXCEL_SERIAL_MAX = 20000, 80000

_DATE_STR_PATTERNS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日",
    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
)


def normalize_date_cell(value) -> str:
    """表格日期单元格 → YYYY-MM-DD（四.2，2026-09-30）。

    - datetime/date 对象（openpyxl 已按 Excel 日期格式解析）→ 直接格式化；
    - 纯数字且落在 Excel 序列号合理区间 → 按 1900 日期体系换算；
    - 常见字符串格式（- / . 年月日、带时间）→ 规范化；
    - 空值/无法解析 → 空串（调用方计数，不用文件日期静默替代）。"""
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{1,7}(\.0+)?", text):
        serial = int(float(text))
        if _EXCEL_SERIAL_MIN <= serial <= _EXCEL_SERIAL_MAX:
            return (_EXCEL_EPOCH + datetime.timedelta(days=serial)).isoformat()
    for fmt in _DATE_STR_PATTERNS:
        try:
            return datetime.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def validate_mapping(mapping: object) -> dict[str, str]:
    # HTTP 层 column_mapping 以 multipart Form 字符串到达（前端
    # JSON.stringify），此处必须先反序列化——直接要求 dict 会让
    # 全部经 API 的逐行导入 400。
    if isinstance(mapping, (str, bytes)):
        try:
            mapping = json.loads(mapping)
        except ValueError as exc:
            raise TableParseError("column_mapping 不是合法 JSON") from exc
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
) -> tuple[dict, str] | None:
    """一行 → BreadthManualRecord 字段。空标题返回 None（调用方跳过计数）。

    每条记录带 source_ref（原文件/工作表/行号）满足溯源要求。日期列按
    normalize_date_cell 规范化（Excel 序列号/中文日期/带时间格式）；
    行日期缺失/不合法时不再用文件日期静默替代（四.2，2026-09-30）——
    fallback_date 仅作显式兜底参数保留，前端逐行模式已不再提交文件级日期。
    """
    title = str(row.get(mapping["title"], "") or "").strip()
    if not title:
        return None
    date = ""
    # 三.3：空值（None/空白）与非法格式区分计数，不用文件日期静默兜底
    date_state = "missing"
    if "date" in mapping:
        raw_date = row.get(mapping["date"], "")
        if raw_date is None or not str(raw_date).strip():
            date_state = "missing"
        else:
            date_state = "invalid"
            date = normalize_date_cell(raw_date)
            if date:
                date_state = "valid"
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
    ), date_state


def import_rows(
    db,
    record,
    sheets: list[TableSheet],
    mapping: dict[str, str],
    *,
    fallback_date: str | None,
    category_fallback: str | None,
    in_breadth_nav: bool = True,
) -> dict:
    """逐行入库：去重（包内 + 撞库）→ breadth_manual_records + 索引任务。

    in_breadth_nav（三.1，2026-09-30）：行业/ATSC 逐行导入默认 False——
    行记录保留原栏目与门户检索，不进入主导航广度列表；勾选
    sync_upload_to_breadth 时为 True（同时进广度，保持原栏目）。
    GitHub 增量包通道不受影响（其记录默认 True）。

    不重复入库：同内容哈希的行（包内重复或库内已存在）跳过并计数。"""
    from app.models.breadth_manual_record import BreadthManualRecord
    from app.services.breadth_index_queue import enqueue_record_upserts

    existing_hashes = set(
        db.scalars(select(BreadthManualRecord.content_hash)).all()
    )
    seen_hashes: set[str] = set()
    created: list[BreadthManualRecord] = []
    skipped_empty = skipped_duplicate = 0
    rows_missing_date = rows_invalid_date = 0
    for sheet in sheets:
        # 三.3：行号逐工作表对数据行从 1 重新计数（source_ref.row 不跨表累计）
        row_no = 0
        for row in sheet.rows:
            row_no += 1
            packed = row_to_record_fields(
                row, mapping,
                upload_id=record.id, user_id=record.submitted_by,
                fallback_date=fallback_date, category_fallback=category_fallback,
                source_file=record.original_filename, sheet_name=sheet.name, row_no=row_no,
            )
            if packed is None:
                skipped_empty += 1
                continue
            fields, date_state = packed
            if date_state == "missing":
                rows_missing_date += 1  # 行日期为空（照常入库）
            elif date_state == "invalid":
                rows_invalid_date += 1  # 行日期有内容但无法解析（照常入库）
            digest = fields["content_hash"]
            if digest in seen_hashes or digest in existing_hashes:
                skipped_duplicate += 1
                continue
            seen_hashes.add(digest)
            fields["in_breadth_nav"] = in_breadth_nav  # 三.1：主导航广度开关
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
        "rows_missing_date": rows_missing_date,
        "rows_invalid_date": rows_invalid_date,
    }

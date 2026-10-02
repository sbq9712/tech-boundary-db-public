"""表格逐行导入（六节）：Excel/CSV 每行一个情报，不要求文件级日期。

- 逐行模式：openpyxl（xlsx）/csv 模块（自动识别 UTF-8/GBK 编码）按单元格
  读取真实表格行——绝不拿 Docling 文档切块冒充行数据；
- 列映射/预览：row-preview 返回工作表名、表头与前 N 行，前端映射后回传；
- 溯源：每条记录的 source_ref 记录 原文件/工作表/行号；
- 空标题行跳过；日期列可选（缺失回退上传日期）。
"""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import func, select, text

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
    # 物理行号（任务三 3.2）：与 rows 按下标对齐——Excel 为工作表物理行号
    # （表头前空行计入），CSV 为记录起始物理行号（含引号内换行的累计）。
    # source_ref.row 必须能指回原文件位置，供校验报错与历史修复对行。
    row_nos: list[int] = field(default_factory=list)


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
    try:
        header_raw = next(reader)
    except StopIteration:
        raise TableParseError("CSV 文件为空")
    headers = [str(h or "").strip() for h in header_raw]
    if not any(headers):
        raise TableParseError("CSV 首行没有可用表头")
    sheet = TableSheet(name="csv", headers=headers)
    # 物理行号（3.2）：reader.line_num 为累计已消费物理行数（含引号内换行）。
    # 每条记录的起始物理行 = 上一条记录结束后的累计行数 + 1。
    prev_end = reader.line_num  # 表头消耗的行数
    for raw in reader:
        start_line = prev_end + 1
        prev_end = reader.line_num  # 本记录（含引号内换行）消耗后的累计
        if not any(str(c or "").strip() for c in raw):
            continue  # 整行为空：跳过（物理行号仍推进）
        row = {}
        for i, header in enumerate(headers):
            if header:
                row[header] = str(raw[i]).strip() if i < len(raw) else ""
        sheet.rows.append(row)
        sheet.row_nos.append(start_line)
        if len(sheet.rows) > MAX_ROWS:
            raise TableParseError(
                f"CSV 数据行超过上限（{MAX_ROWS} 行）：请拆分文件后上传，"
                f"拒绝静默截断（已读到第 {start_line} 行仍有数据）")
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
            for row_no, row in enumerate(ws.iter_rows(values_only=True), start=1):
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
                # 物理行号（3.2）：Excel 按工作表物理行计——表头前空行与
                # 表中空行天然计入 row_no，source_ref 能指回原文件行。
                sheet.row_nos.append(row_no)
                if len(sheet.rows) > MAX_ROWS:
                    raise TableParseError(
                        f"工作表「{sheet.name}」数据行超过上限（{MAX_ROWS} 行）："
                        f"请拆分文件后上传，拒绝静默截断（第 {row_no} 行仍有数据）")
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
                # 物理行号（任务三 3.1）：预览行与原文件行对齐展示，
                # 前端可提前提示类型问题（后端校验为准）。
                "row_nos": s.row_nos[:PREVIEW_ROWS],
            }
            for s in sheets
        ]
    }


# 列映射允许的语义槽位（title 必填，其余可选）
MAPPING_SLOTS = ("title", "date", "category", "url", "source", "level", "body", "summary", "type")

# ── 情报类型严格化（任务三，2026-10-02）─────────────────────────────────
# 「其他广度情报」逐行表格以「情报类型」列为权威业务输入：
# - 列名识别只做【去空白后全等】匹配，禁子串匹配（避免「新闻类型」
#   「分类」「行业类别」被误认成类型列）；
# - 取值映射固定：新闻→news、文献→literature；仅允许去空白
#   （含全角空格/制表符），错别字/未知值一律非法，不猜测；
# - 严格模式（require_type，仅 breadth/other 入口）下缺映射/列不存在/
#   任一非空数据行类型为空或非法 → 整文件校验错误，不提交任何行。
TYPE_SLOT = "type"
TYPE_COLUMN_EXACT = ("情报类型",)
TYPE_VALUES = {"新闻": "news", "文献": "literature"}
DEFAULT_INTELLIGENCE_TYPE = "news"  # 仅严格模式以外（行业/ATSC 未映射时）沿用


def strip_type_ws(value) -> str:
    """类型单元格取值规范化：仅去空白（半角/全角空格、制表符、换行）。"""
    return str(value if value is not None else "").strip(" \t\r\n　\v\f")


def resolve_type_value(raw) -> str | None:
    """类型原值 → news/literature；无法识别返回 None（调用方决定报错或回退）。"""
    norm = strip_type_ws(raw)
    return TYPE_VALUES.get(norm)


def compute_content_hash_v2(
    title: str, document_date: str, url: str,
    body: str, summary: str, intelligence_type: str,
) -> str:
    """v2 内容指纹（导入链唯一实现，修复脚本复用同一实现保证一致）。

    纳入 intelligence_type（任务三 3.3）：类型修正必须可识别为「内容变化」。
    注意：入库时以「原始值」计算；记录列存 20000 截断值——超长文本时
    从库列重算得到的哈希与入库哈希不同（只会触发多余重索引，绝不吞变化）。
    """
    return hashlib.sha256(
        json.dumps(
            {"t": title, "d": document_date, "u": url, "b": body, "s": summary,
             "i": intelligence_type},
            ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _identity_key(title: str, date: str, url: str) -> str:
    """行记录统一身份：与 GitHub 增量包链路同源——sha256(json([t,d,u]))[:16]。

    （任务三 3.3 / 任务二 2.1）内容哈希承担「内容是否变化」，身份键承担
    「是不是同一条情报」：类型修正改变内容哈希但不改变身份——既不会被
    「无变化」吞掉，也不会产生重复记录。
    """
    return hashlib.sha256(
        json.dumps([title, date, url], ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]

# Excel 日期序列号合理范围（1900-01-01 起）：1990-01-01 ≈ 32874，2079 ≈ 65380
_EXCEL_EPOCH = _dt.date(1899, 12, 30)
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
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{1,7}(\.0+)?", text):
        serial = int(float(text))
        if _EXCEL_SERIAL_MIN <= serial <= _EXCEL_SERIAL_MAX:
            return (_EXCEL_EPOCH + _dt.timedelta(days=serial)).isoformat()
    for fmt in _DATE_STR_PATTERNS:
        try:
            return _dt.datetime.strptime(text, fmt).date().isoformat()
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
    # 情报类型（任务三 3.1/3.3）：映射了 type 列则按 TYPE_VALUES 严格转换。
    # 严格模式（require_type）下非法/空值已在 validate_row_types 预检阶段
    # 整文件报错，此处只做安全回退（非严格入口沿用 news 默认，行为不变）。
    intelligence_type = DEFAULT_INTELLIGENCE_TYPE
    if TYPE_SLOT in mapping:
        intelligence_type = (
            resolve_type_value(row.get(mapping[TYPE_SLOT], "")) or DEFAULT_INTELLIGENCE_TYPE)

    # content_hash 纳入类型（3.3）：类型修正必须可被识别为「内容变化」，
    # 不被「无变化」吞掉——身份去重由 _identity_key 承担，不会产生重复。
    content_hash = compute_content_hash_v2(
        title, date, url, body, summary, intelligence_type)
    return dict(
        upload_id=upload_id,
        user_id=user_id,
        title=title[:500],
        body=(body or summary)[:20000] or None,
        category=category[:500] or None,
        document_date=date[:32] or None,
        level=level,
        intelligence_type=intelligence_type,
        source_name=str(row.get(mapping.get("source", ""), "") or "").strip()[:255]
        or source_file[:255],
        url=url[:1024] or None,
        key_parameters=[],
        ai_summary=summary[:20000] or None,
        source_version=1,
        content_hash=content_hash,
        source_ref={"file": source_file, "sheet": sheet_name, "row": row_no},
    ), date_state


def validate_row_types(
    sheets: list[TableSheet],
    mapping: dict[str, str],
    *,
    require_type: bool,
    source_file: str,
    max_errors: int = 20,
) -> list[str]:
    """（任务三 3.2）入库前全量类型校验：纯函数、无 DB、覆盖所选工作表全部行。

    返回错误消息列表（空 = 通过）。严格模式（「其他广度情报」逐行导入）下：
    - 缺 type 映射 / 映射列不在所选工作表表头 → 文件级错误；
    - 任一【非空数据行】类型为空或非法 → 行级错误（物理行号/列名/原值/原因）。
    完全空白行可跳过；其他字段为空不豁免类型错误。"""
    errors: list[str] = []
    if not require_type:
        return errors
    if TYPE_SLOT not in mapping or not str(mapping.get(TYPE_SLOT) or "").strip():
        errors.append(
            f"[{source_file}] 缺少「情报类型」列映射：请在导入配置中将"
            f"「情报类型」槽位映射到表格的 情报类型 列（取值仅允许：新闻/文献）")
        return errors
    type_column = str(mapping[TYPE_SLOT]).strip()
    for sheet in sheets:
        if type_column not in sheet.headers:
            errors.append(
                f"[{source_file}] 工作表「{sheet.name}」不存在映射的「情报类型」列："
                f"「{type_column}」（表头：{'、'.join((h or '（空）') for h in sheet.headers[:12])}）")
            continue
        if sheet.headers.count(type_column) > 1:
            errors.append(
                f"[{source_file}] 工作表「{sheet.name}」存在重复的「{type_column}」列名"
                f"（{sheet.headers.count(type_column)} 个）：无法确定映射目标，请修正表头")
            continue
        for row, row_no in zip(sheet.rows, sheet.row_nos):
            norm = strip_type_ws(row.get(type_column, ""))
            if not norm:
                errors.append(
                    f"[{source_file}] 工作表「{sheet.name}」第 {row_no} 行："
                    f"「{type_column}」列情报类型为空（仅允许：新闻/文献）")
            elif norm not in TYPE_VALUES:
                errors.append(
                    f"[{source_file}] 工作表「{sheet.name}」第 {row_no} 行："
                    f"「{type_column}」列情报类型非法：原值「{norm}」（仅允许：新闻/文献）")
            if len(errors) >= max_errors:
                errors.append(f"[{source_file}] 类型错误过多，仅显示前 {max_errors} 条…")
                return errors
    return errors


def import_rows(
    db,
    record,
    sheets: list[TableSheet],
    mapping: dict[str, str],
    *,
    fallback_date: str | None,
    category_fallback: str | None,
    in_breadth_nav: bool = True,
    require_type: bool = False,
    origin_section: str = "breadth",
) -> dict:
    """逐行入库：全量校验 → 身份去重/更新 → breadth_manual_records + 索引任务。

    in_breadth_nav（三.1，2026-09-30）：行业/ATSC 逐行导入默认 False——
    行记录保留原栏目与门户检索，不进入主导航广度列表；勾选
    sync_upload_to_breadth 时为 True（同时进广度，保持原栏目）。
    GitHub 增量包通道不受影响（其记录默认 True）。

    require_type（任务三 3.2，2026-10-02）：仅「其他广度情报」逐行导入为
    True——入库前对所选工作表全部行做类型校验，任一错误抛 TableParseError
    （调用方清理路径整文件回滚：不产生任何部分入库行/索引任务/可见结果）。

    去重/更新语义（任务三 3.3 / 任务二 2.1）：
    - 行身份 = sha256(json([t,d,u]))[:16]（与 GitHub 通道 stable_id 同源）；
    - 撞身份且内容（含类型）完全相同 → skipped_duplicate；
    - 撞身份但内容/类型不同（如类型修正、正文更新）→ UPDATE 原记录并
      重入队索引，计 updated——类型修正不被「无变化」吞掉、不产生重复情报；
    - 全局正文哈希去重废止（避免不同来源的合法记录被误吞）。"""
    from app.models.breadth_manual_record import BreadthManualRecord
    from app.services.breadth_index_queue import enqueue_record_upserts

    # ── 第一阶段：全量类型校验（无 DB 写入；失败抛错整文件不提交） ──
    type_errors = validate_row_types(
        sheets, mapping, require_type=require_type, source_file=record.original_filename)
    if type_errors:
        raise TableParseError(
            f"情报类型校验未通过（{len(type_errors)} 处），本文件未导入任何行：\n"
            + "\n".join(type_errors))

    # ── 并发仲裁（Codex P1）：行导入串行化——两个并发请求同导同一身份时，
    # 后者在锁内重读身份索引，不会再插入重复行。事务级咨询锁，提交/回滚
    # 自动释放。GitHub feed 通道有自己的 stable_id 仲裁，不经此锁。 ──
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('row-import'))"))

    # ── 库内既有记录身份索引（stable_id 优先；旧行无 stable_id 按同公式现算）。
    #    三.2（2026-10-03）来源命名空间：身份匹配只在【同 origin】记录范围内
    #    进行——行业/ATSC/广度是独立数据源，同名同日期空 URL 的跨源行不得
    #    互相覆盖（历史缺陷：industry 记录的 body 被 atsc 表格静默改写、
    #    来源字段自相矛盾、且不新建独立 ATSC 记录）。旧数据 origin_section
    #    为 NULL 时按 breadth 语义兼容（与 _rec_origin_section 读取侧一致）。 ──
    _import_origin = origin_section if origin_section in ("breadth", "industry", "atsc") else "breadth"
    existing_rows = db.execute(
        select(
            BreadthManualRecord.id,
            BreadthManualRecord.stable_id,
            BreadthManualRecord.title,
            BreadthManualRecord.document_date,
            BreadthManualRecord.url,
        ).where(
            func.coalesce(BreadthManualRecord.origin_section, "breadth") == _import_origin
        )
    ).all()
    identity_to_id: dict[str, object] = {}
    for er in existing_rows:
        ident = str(er.stable_id or "") or _identity_key(
            str(er.title or ""), str(er.document_date or ""), str(er.url or ""))
        identity_to_id.setdefault(ident, er.id)

    # 语义比较键（Codex P0/P1）：content_hash 公式升级（纳入类型）与
    # source_name 的文件名回填不构成「变化」——避免存量行重导产生churn。
    # source_name 不参与判等，但真实更新时照常写入。
    _SEMANTIC_KEYS = ("title", "body", "category", "document_date", "level",
                      "intelligence_type", "url", "ai_summary")
    created: list[BreadthManualRecord] = []
    updated_records: list[BreadthManualRecord] = []
    skipped_empty = skipped_duplicate = updated_count = skipped_upstream = 0
    rows_missing_date = rows_invalid_date = 0
    for sheet in sheets:
        for row, row_no in zip(sheet.rows, sheet.row_nos):
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
            identity = _identity_key(
                str(fields["title"]), str(fields["document_date"] or ""),
                str(fields["url"] or ""))
            existing = identity_to_id.get(identity)
            if existing is not None:
                existing_rec = existing if isinstance(existing, BreadthManualRecord) \
                    else db.get(BreadthManualRecord, existing)
                if existing_rec is None:
                    identity_to_id.pop(identity, None)
                else:
                    # 语义比较（而非哈希比较）：content_hash 公式升级（纳入
                    # 类型）不构成「变化」——存量行重导不产生无谓更新。
                    same_semantics = all(
                        getattr(existing_rec, key, None) == fields.get(key)
                        for key in _SEMANTIC_KEYS)
                    if same_semantics:
                        skipped_duplicate += 1
                        # 旧行身份回填：收敛到显式 stable_id（不动其余字段）
                        if not existing_rec.stable_id:
                            existing_rec.stable_id = identity
                        # 三.2：同源重导只改变「同步到广度」投影开关时，
                        # 投影如实跟随本次导入（幂等：重导相同开关无 churn；
                        # 纯展示位，不触发索引重入队）。
                        existing_rec.in_breadth_nav = in_breadth_nav
                        continue
                    if existing_rec.feed_key_digest:
                        # Codex P1：feed 通道管理的行（GitHub 增量包 UPDATE/
                        # DELETE 链）不因手工表格导入被覆盖——保持上游数据，
                        # 如实计数，导入方可核对后再经包通道修正。
                        skipped_upstream += 1
                        continue
                    # 同身份新内容/类型修正：UPDATE 原记录，计数 updated 并
                    # 重入队索引。三.2：来源字段一致性——source_ref/source_name/
                    # upload_id/user_id/属主栏目一并随本次修订文件对齐，
                    # 不留「body 是新文件、属主还是旧文件」的矛盾来源
                    # （同源内修订，origin 不变；GitHub feed 行已在上面
                    # skipped_upstream 保护，不会被表格导入改写）。
                    for key in _SEMANTIC_KEYS + ("content_hash",):
                        setattr(existing_rec, key, fields[key])
                    existing_rec.source_version = (existing_rec.source_version or 1) + 1
                    existing_rec.source_ref = fields["source_ref"]
                    existing_rec.source_name = fields.get("source_name") or existing_rec.source_name
                    existing_rec.upload_id = record.id
                    existing_rec.user_id = record.submitted_by
                    existing_rec.in_breadth_nav = in_breadth_nav
                    # 修正溯源（Codex P2）：记录最近一次表格修正的来处，
                    # 状态明细可解释「谁在哪个文件哪一行改了它」。
                    audit = dict(existing_rec.record_json or {})
                    trail = audit.setdefault("row_update_audit", [])
                    trail.append({
                        "file": record.original_filename, "sheet": sheet.name,
                        "row": row_no, "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                        "by": record.submitted_by,
                    })
                    audit["row_update_audit"] = trail[-10:]
                    existing_rec.record_json = audit
                    updated_records.append(existing_rec)
                    updated_count += 1
                    continue
            fields["stable_id"] = identity
            fields["in_breadth_nav"] = in_breadth_nav  # 三.1：主导航广度开关
            # 任务二 2.1：原始栏目归属（行业/ATSC 逐行导入保留原栏目，
            # 同步广度只改展示入口）
            fields["origin_section"] = origin_section if origin_section in ("breadth", "industry", "atsc") else "breadth"
            new_rec = BreadthManualRecord(**fields)
            created.append(new_rec)
            # 包内后续同身份行走 UPDATE/去重分支（同内容→duplicate，不同→update）
            identity_to_id[identity] = new_rec
    db.add_all(created)
    db.flush()
    to_enqueue = created + updated_records
    if to_enqueue:
        enqueue_record_upserts(db, to_enqueue)
    return {
        "rows_total": sum(len(s.rows) for s in sheets),
        "imported": len(created),
        "updated": updated_count,
        "skipped_empty": skipped_empty,
        "skipped_duplicate": skipped_duplicate,
        "skipped_upstream_conflict": skipped_upstream,
        "rows_missing_date": rows_missing_date,
        "rows_invalid_date": rows_invalid_date,
    }

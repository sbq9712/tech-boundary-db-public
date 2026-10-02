"""任务三（3.1/3.2/3.3）：其他广度情报逐行表格「情报类型」严格化——功能测试。

覆盖：类型列精确识别/映射取值、混合 news/literature、全量先校验后入库
（第 21 行之后的错误也要整文件拒绝）、缺列/空值/非法值报错上下文
（文件/工作表/物理行号/列名/原值/原因）、CSV 引号内换行的物理行号、
表头前空行、超限显式报错（不静默截断）、幂等重导、仅类型修正不被吞掉、
身份去重不产生重复情报、行业/ATSC 入口不受严格模式影响。
"""
from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.uploaded_file import UploadedFile
from app.services.table_rows import (
    MAX_ROWS,
    TYPE_SLOT,
    TYPE_VALUES,
    TableParseError,
    import_rows,
    parse_table,
    preview,
    resolve_type_value,
    strip_type_ws,
    validate_row_types,
)

CLEANUP: list[str] = []


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        for rid in CLEANUP:
            db.execute(text("DELETE FROM breadth_index_tasks WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM breadth_manual_records WHERE upload_id=:i"), {"i": rid})
            db.execute(text("DELETE FROM uploaded_files WHERE id=:i"), {"i": rid})
        db.execute(text("DELETE FROM breadth_manual_records WHERE user_id='type-test'"))
        db.commit()
    finally:
        db.close()
        CLEANUP.clear()


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch):
    monkeypatch.setenv("TECHDB_BREADTH_INDEX_WORKER_ENABLED", "false")


def _mk_upload(db, filename="情报表.xlsx", section="breadth", source="other"):
    rec = UploadedFile(
        stored_filename=f"objects/xx/{uuid.uuid4().hex}",
        original_filename=filename,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        checksum_sha256=uuid.uuid4().hex,
        storage_status="stored",
        title=filename,
        title_source="manual",
        primary_section=section,
        breadth_source=source,
        classification_status="classified",
        embedding_status="queued",
        submitted_by="type-test",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    CLEANUP.append(str(rec.id))
    return rec


def _csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def _xlsx_bytes(rows_by_sheet: dict[str, list[list]], blank_leading=0) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in rows_by_sheet.items():
        ws = wb.create_sheet(title=name)
        for _ in range(blank_leading):
            ws.append([])
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


BASE_MAPPING = {"title": "标题", "date": "日期", "url": "链接", TYPE_SLOT: "情报类型"}


def _import(db, data, filename, mapping, require_type=True, section="breadth", source="other",
            in_breadth_nav=True):
    upload = _mk_upload(db, filename=filename, section=section, source=source)
    sheets = parse_table(data, filename)
    stats = import_rows(
        db, upload, sheets, mapping, fallback_date=None, category_fallback=None,
        in_breadth_nav=in_breadth_nav, require_type=require_type)
    db.commit()
    return upload, stats


def _rows(db, upload_id=None):
    from app.models.breadth_manual_record import BreadthManualRecord
    from sqlalchemy import select
    q = select(BreadthManualRecord).where(BreadthManualRecord.user_id == "type-test")
    if upload_id is not None:
        q = q.where(BreadthManualRecord.upload_id == upload_id)
    return db.scalars(q.order_by(BreadthManualRecord.created_at, BreadthManualRecord.title)).all()


# ── 3.1 取值映射 ─────────────────────────────────────────────────────────

def test_type_value_map_strict():
    assert TYPE_VALUES == {"新闻": "news", "文献": "literature"}
    assert resolve_type_value("新闻") == "news"
    assert resolve_type_value(" 文献 ") == "literature"          # 仅去空白
    assert resolve_type_value("文献　") == "literature"          # 全角空格
    assert resolve_type_value("新wen") is None                   # 错别字不猜
    assert resolve_type_value("论文") is None                    # 未知值不猜
    assert resolve_type_value("") is None
    assert resolve_type_value(None) is None


def test_type_column_recognition_not_substring():
    """「情报类型」列名精确识别；「新闻类型/分类/行业类别」不得被当成类型列。"""
    csv_data = _csv_bytes(
        "标题,新闻类型\n"
        "甲,新闻\n"
    )
    sheets = parse_table(csv_data, "t.csv")
    mapping = {"title": "标题"}  # 未映射 type
    errs = validate_row_types(sheets, mapping, require_type=True, source_file="t.csv")
    assert errs and "缺少「情报类型」列映射" in errs[0]
    # 新闻类型 列存在但值合法——也不得被自动当类型列（必须显式映射）
    csv_data2 = _csv_bytes("标题,新闻类型\n甲,新闻\n")
    sheets2 = parse_table(csv_data2, "t.csv")
    errs2 = validate_row_types(sheets2, {"title": "标题", TYPE_SLOT: "新闻类型"},
                               require_type=True, source_file="t.csv")
    # 显式映射到「新闻类型」列：值合法即可通过（用户显式选择优先），
    # 但自动猜测（无映射）必须报缺列。
    assert errs2 == []


def test_mixed_types_in_one_file(db):
    data = _csv_bytes(
        "标题,日期,链接,情报类型\n"
        "新闻甲,2026-09-01,https://a/1,新闻\n"
        "文献乙,2026-09-02,https://a/2,文献\n"
    )
    upload, stats = _import(db, data, "mix.csv", BASE_MAPPING)
    assert stats["imported"] == 2
    rows = _rows(db, upload.id)
    by_title = {r.title: r for r in rows}
    assert by_title["新闻甲"].intelligence_type == "news"
    assert by_title["文献乙"].intelligence_type == "literature"


# ── 3.2 全量校验、物理行号、原子性 ──────────────────────────────────────

def test_error_after_preview_row_20_rejects_whole_file(db):
    """第 21 行类型非法：预览只显示 20 行，但校验覆盖全部——整文件拒绝。"""
    lines = ["标题,情报类型"]
    for i in range(25):
        lines.append(f"情报{i},新闻" if i < 20 else f"情报{i},报导")
    data = _csv_bytes("\n".join(lines) + "\n")
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "late.csv", BASE_MAPPING)
    msg = str(ei.value)
    assert "情报22" in msg or "第 22 行" in msg or "报导" in msg
    assert "原值「报导」" in msg
    assert _rows(db) == []  # 无任何部分入库


def test_missing_type_column_error(db):
    data = _csv_bytes("标题,日期\n甲,2026-09-01\n")
    mapping = {"title": "标题", "date": "日期"}
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "nocol.csv", mapping)
    assert "缺少「情报类型」列映射" in str(ei.value)
    assert _rows(db) == []


def test_mapped_column_missing_in_sheet_error(db):
    data = _csv_bytes("标题\n甲\n")
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "mismatch.csv", BASE_MAPPING)
    assert "不存在映射的「情报类型」列" in str(ei.value)


def test_empty_type_value_error_with_context(db):
    """空类型 + 物理行号上下文；表头前空行计入行号。"""
    data = _csv_bytes(
        "标题,情报类型\n"
        "甲,新闻\n"
        "乙,\n"
    )
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "empty.csv", BASE_MAPPING)
    msg = str(ei.value)
    assert "第 3 行" in msg          # 物理行（表头=1，甲=2，乙=3）
    assert "情报类型" in msg
    assert "为空" in msg


def test_blank_row_skipped_but_counted_physically(db):
    """完全空白行可跳过；其后数据行报错时用真实物理行号。"""
    data = _csv_bytes(
        "标题,情报类型\n"
        "甲,新闻\n"
        "\n"
        "乙,综述\n"
    )
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "blank.csv", BASE_MAPPING)
    assert "第 4 行" in str(ei.value)


def test_csv_quoted_newline_physical_rows(db):
    """CSV 引号内换行：记录起始物理行号按含换行累计。"""
    data = _csv_bytes(
        '标题,情报类型\n'
        '"多行\n正文",新闻\n'
        '乙,评论\n'
    )
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "quoted.csv", BASE_MAPPING)
    # 「乙」的物理起始行 = 表头(1) + 多行记录占 2 行(2-3) → 4
    assert "第 4 行" in str(ei.value)


def test_xlsx_physical_rows_with_leading_blank(db):
    openpyxl = pytest.importorskip("openpyxl")
    data = _xlsx_bytes({"表一": [
        ["标题", "情报类型"],
        ["甲", "新闻"],
        ["乙", "综述"],
    ]}, blank_leading=2)  # 表头前 2 行空行 → 表头在第 3 行
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "lead.xlsx", BASE_MAPPING)
    assert "第 5 行" in str(ei.value)  # 2 空行 + 表头(3) + 甲(4) + 乙(5)


def test_over_limit_rejected_not_truncated(db):
    assert MAX_ROWS == 20_000
    lines = ["标题,情报类型"] + [f"情报{i},新闻" for i in range(MAX_ROWS + 1)]
    data = _csv_bytes("\n".join(lines) + "\n")
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "over.csv", BASE_MAPPING)
    assert "超过上限" in str(ei.value)
    assert "拒绝静默截断" in str(ei.value)
    assert _rows(db) == []


def test_no_index_tasks_on_validation_failure(db):
    from sqlalchemy import func, select as sa_select
    from app.models.index_task import IndexTask
    data = _csv_bytes("标题,情报类型\n甲,新闻\n乙,非法\n")
    upload = _mk_upload(db, filename="atomic.csv")
    sheets = parse_table(data, "atomic.csv")
    with pytest.raises(TableParseError):
        import_rows(db, upload, sheets, BASE_MAPPING, fallback_date=None,
                    category_fallback=None, require_type=True)
    n = db.scalar(sa_select(func.count(IndexTask.id)).where(IndexTask.upload_id == upload.id))
    assert n == 0


def test_industry_atsc_not_strict(db):
    """行业/ATSC 入口不受严格类型要求影响（未映射类型列照常导入）。"""
    data = _csv_bytes("标题,日期\n行业甲,2026-09-01\n")
    upload, stats = _import(db, data, "industry.csv", {"title": "标题", "date": "日期"},
                            require_type=False, section="industry", source="",
                            in_breadth_nav=False)
    assert stats["imported"] == 1
    rows = _rows(db, upload.id)
    assert rows[0].intelligence_type == "news"  # 非严格入口沿用默认
    assert rows[0].in_breadth_nav is False


# ── 3.3 幂等/类型修正/身份去重 ──────────────────────────────────────────

def test_reimport_same_file_idempotent(db):
    data = _csv_bytes("标题,链接,情报类型\n甲,https://a/1,新闻\n")
    upload1, stats1 = _import(db, data, "again.csv", BASE_MAPPING)
    assert stats1["imported"] == 1
    upload2, stats2 = _import(db, data, "again.csv", BASE_MAPPING)
    assert stats2["imported"] == 0
    assert stats2["skipped_duplicate"] == 1
    assert len(_rows(db)) == 1  # 不产生重复情报


def test_type_only_correction_not_swallowed(db):
    """同身份仅改类型：hash 含类型 → 不判「无变化」，UPDATE 计数，无重复。"""
    data_v1 = _csv_bytes("标题,链接,情报类型\n甲,https://a/1,新闻\n")
    upload1, stats1 = _import(db, data_v1, "fix.csv", BASE_MAPPING)
    assert stats1["imported"] == 1
    data_v2 = _csv_bytes("标题,链接,情报类型\n甲,https://a/1,文献\n")
    upload2, stats2 = _import(db, data_v2, "fix.csv", BASE_MAPPING)
    assert stats2["imported"] == 0
    assert stats2["updated"] == 1
    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0].intelligence_type == "literature"
    assert rows[0].source_version == 2
    assert str(rows[0].upload_id) == str(upload1.id)  # 属主不转移


def test_type_correction_requeues_index(db):
    from app.models.index_task import IndexTask
    from sqlalchemy import select as sa_select
    data_v1 = _csv_bytes("标题,链接,情报类型\n甲,https://a/1,新闻\n")
    upload1, _ = _import(db, data_v1, "rq.csv", BASE_MAPPING)
    tasks1 = db.scalars(sa_select(IndexTask).where(IndexTask.upload_id.in_(
        [upload1.id]))).all()
    data_v2 = _csv_bytes("标题,链接,情报类型\n甲,https://a/1,文献\n")
    upload2, _ = _import(db, data_v2, "rq.csv", BASE_MAPPING)
    tasks2 = db.scalars(sa_select(IndexTask).where(IndexTask.upload_id.in_(
        [upload1.id, upload2.id]))).all()
    assert len(tasks2) == len(tasks1)  # 同一记录同一任务行（覆盖式重入队）
    upserts = [t for t in tasks2 if t.op == "upsert"]
    assert upserts and upserts[0].status == "pending"  # 重入队待处理


def test_same_content_different_type_not_merged_globally(db):
    """不同来源/不同身份的同正文记录不被全局正文哈希吞掉。"""
    data = _csv_bytes(
        "标题,链接,情报类型\n"
        "甲,https://a/1,新闻\n"
        "甲,https://a/2,文献\n"  # 同标题同正文，不同 URL=不同身份
    )
    upload, stats = _import(db, data, "twoid.csv", BASE_MAPPING)
    assert stats["imported"] == 2  # 两条独立情报（真实身份不同）


def test_preview_exposes_row_nos_and_headers():
    data = _csv_bytes("标题,情报类型\n甲,新闻\n乙,文献\n")
    pv = preview(data, "p.csv")
    sheet = pv["sheets"][0]
    assert sheet["row_nos"] == [2, 3]
    assert sheet["total_rows"] == 2


def test_feed_owned_rows_not_clobbered(db):
    """Codex P1：feed 通道（GitHub 增量包）管理的行不被表格导入覆盖。"""
    from app.models.breadth_manual_record import BreadthManualRecord
    # 先经 feed 形态落一条：stable_id + feed_key_digest 非空
    feed_row = BreadthManualRecord(
        upload_id=_mk_upload(db, filename="feed.zip").id,
        user_id="type-test",
        title="已有情报",
        body="旧正文",
        document_date="2026-09-01",
        url="https://a/9",
        intelligence_type="news",
        stable_id=_identity("已有情报", "2026-09-01", "https://a/9"),
        feed_key_digest="feedowned",
        source_version=1,
    )
    db.add(feed_row)
    db.commit()
    # 表格导入同身份不同正文
    data = _csv_bytes("标题,日期,链接,情报类型\n已有情报,2026-09-01,https://a/9,文献\n")
    upload, stats = _import(db, data, "clobber.csv", BASE_MAPPING)
    assert stats["imported"] == 0
    assert stats["updated"] == 0
    assert stats["skipped_upstream_conflict"] == 1
    db.refresh(feed_row)
    assert feed_row.intelligence_type == "news"   # 未被覆盖
    assert feed_row.body == "旧正文"


def _identity(t, d, u):
    import hashlib, json as _json
    return hashlib.sha256(
        _json.dumps([t, d, u], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def test_legacy_hash_rows_no_churn_on_reimport(db):
    """Codex P0：存量行是旧五字段哈希——语义相同重导不产生更新churn。"""
    from app.models.breadth_manual_record import BreadthManualRecord
    legacy = BreadthManualRecord(
        upload_id=_mk_upload(db, filename="legacy.csv").id,
        user_id="type-test",
        title="旧情报",
        body="正文X",
        document_date="2026-09-01",
        url="https://a/8",
        intelligence_type="news",
        source_version=1,
        # 模拟旧公式 content_hash（不含类型）
    )
    db.add(legacy)
    db.commit()
    data = _csv_bytes("标题,日期,链接,情报类型,正文\n旧情报,2026-09-01,https://a/8,新闻,正文X\n")
    mapping = dict(BASE_MAPPING); mapping["body"] = "正文"
    upload, stats = _import(db, data, "legacy.csv", mapping)
    assert stats["imported"] == 0
    assert stats["updated"] == 0            # 语义相同：不是更新
    assert stats["skipped_duplicate"] == 1
    db.refresh(legacy)
    assert legacy.stable_id == _identity("旧情报", "2026-09-01", "https://a/8")  # 身份回填


def test_duplicate_type_header_rejected(db):
    data = _csv_bytes("标题,情报类型,情报类型\n甲,新闻,文献\n")
    with pytest.raises(TableParseError) as ei:
        _import(db, data, "dupcol.csv", BASE_MAPPING)
    assert "重复" in str(ei.value)

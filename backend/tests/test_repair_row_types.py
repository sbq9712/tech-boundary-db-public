"""任务三 3.4：历史「情报类型」修复脚本——功能测试（真实文件回读）。

场景构造：正常导入（带类型）→ 人为清空类型模拟存量 → 修复脚本
dry-run（只列计划）→ backup（JSON 落盘）→ 执行（UPDATE+重入队）→
幂等重跑（no-op）。另覆盖：行身份漂移 → pending 不猜测。
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.db.session import SessionLocal
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.index_task import IndexTask
from app.models.uploaded_file import UploadedFile
from app.services.table_rows import import_rows

CLEANUP: list[str] = []


@pytest.fixture(autouse=True)
def _no_worker(monkeypatch):
    monkeypatch.setenv("TECHDB_BREADTH_INDEX_WORKER_ENABLED", "false")


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        from sqlalchemy import text

        for rid in CLEANUP:
            db.execute(
                text("DELETE FROM breadth_index_tasks WHERE upload_id=:i"), {"i": rid})
            db.execute(
                text("DELETE FROM breadth_manual_records WHERE upload_id=:i"), {"i": rid})
            db.execute(
                text("DELETE FROM uploaded_files WHERE id=:i"), {"i": rid})
        db.commit()
    finally:
        db.close()
        CLEANUP.clear()


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


def _mk_xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "情报"
    ws.append(["标题", "日期", "链接", "情报类型", "正文"])
    ws.append(["钙钛矿叠层效率", "2026-09-01", "https://x/1", "新闻", "正文一"])
    ws.append(["固态电池界面", "2026-09-02", "https://x/2", "文献", "正文二"])
    ws.append(["电解质进展", "2026-09-03", "https://x/3", "新闻", "正文三"])
    p = tmp_path / "table.xlsx"
    wb.save(p)
    return p


def _import_and_corrupt(db, tmp_path, monkeypatch, corrupt_values=("新闻原文", "invalid", "news")):
    """正常导入 3 行 → 人为破坏类型模拟存量（非法值/被默认值顶替的错标）。

    库列 NOT NULL default 'news'：存量问题形态是非法串或「文件=文献、
    库=news」的错标——不能用 NULL 模拟。
    """
    xlsx = _mk_xlsx(tmp_path)
    stored_rel = f"objects/{uuid.uuid4().hex}/table.xlsx"
    upload_root = tmp_path / "up"
    (upload_root / stored_rel).parent.mkdir(parents=True, exist_ok=True)
    (upload_root / stored_rel).write_bytes(xlsx.read_bytes())
    monkeypatch.setenv("TECHDB_UPLOAD_DIR", str(upload_root))

    upload = UploadedFile(
        stored_filename=stored_rel,
        original_filename="table.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        checksum_sha256=uuid.uuid4().hex,
        storage_status="stored",
        title="table.xlsx",
        primary_section="breadth",
        breadth_source="other",
        classification_status="classified",
        classification_confidence=1.0,
        classification_source="manual",
        embedding_status="queued",
        submitted_by="repair-test",
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    CLEANUP.append(upload.id)

    mapping = {"title": "标题", "date": "日期", "url": "链接",
               "type": "情报类型", "body": "正文"}
    from app.services.table_rows import parse_table
    sheets = parse_table(xlsx.read_bytes(), "table.xlsx")
    stats = import_rows(
        db, upload, sheets, mapping,
        fallback_date=None, category_fallback=None,
        require_type=True, origin_section="breadth")
    assert stats["imported"] == 3

    recs = db.scalars(
        __import__("sqlalchemy").select(BreadthManualRecord).where(
            BreadthManualRecord.upload_id == upload.id)
        .order_by(BreadthManualRecord.title)
    ).all()
    # 模拟存量：破坏类型（按标题定位：电解质/钙钛矿=新闻，固态=文献）
    for rec, bad in zip(recs, corrupt_values):
        rec.intelligence_type = bad
    db.commit()
    return upload, recs



def _run_script(*args):
    root = Path(__file__).resolve().parent.parent
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "repair_row_intelligence_types.py"), *args],
        capture_output=True, text=True, timeout=120,
    )


def test_repair_dry_run_backup_execute_idempotent(db, tmp_path, monkeypatch):
    upload, recs = _import_and_corrupt(db, tmp_path, monkeypatch)

    # dry-run：2 条可修（1 条非法值 + 1 条「文件=文献、库=新闻原文」错标
    # ——错标检测依赖回读对比）；第 3 条库值 news 与文件「新闻」一致 → no-op
    r = _run_script("--dry-run")
    assert r.returncode == 0, r.stderr
    assert "可修复：2" in r.stdout, r.stdout
    assert "待人工（不猜测）：0" in r.stdout
    assert "-> literature（原值 '文献'）" in r.stdout

    # backup + 执行
    backup = tmp_path / "backup.json"
    r = _run_script("--backup", str(backup))
    assert r.returncode == 0, r.stderr
    assert "修复完成：2" in r.stdout
    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 2
    assert {e["new_type"] for e in payload["entries"]} == {"news", "literature"}

    for rec in recs:
        db.refresh(rec)
    by_title = {r.title: r.intelligence_type for r in recs}
    assert by_title["钙钛矿叠层效率"] == "news"
    assert by_title["固态电池界面"] == "literature"
    assert by_title["电解质进展"] == "news"
    # 重入队：3 条记录有任务
    n = len(
        db.scalars(
            __import__("sqlalchemy").select(IndexTask).where(
                IndexTask.upload_id == upload.id)
        ).all()
    )
    assert n >= 3

    # 幂等：再跑 no-op（全部与文件一致）
    r = _run_script("--dry-run")
    assert r.returncode == 0
    assert "可修复：0" in r.stdout


def test_repair_identity_drift_goes_pending(db, tmp_path, monkeypatch):
    """行身份漂移（标题被改）→ pending 清单，不猜测。"""
    upload, recs = _import_and_corrupt(db, tmp_path, monkeypatch)
    for rec in recs:
        rec.intelligence_type = "invalid"
    # 漂移：改掉一个标题
    recs[0].title = "被人手改过的标题"
    db.commit()

    r = _run_script("--dry-run")
    assert r.returncode == 0, r.stderr
    assert "可修复：2" in r.stdout
    assert "待人工（不猜测）：1" in r.stdout
    assert "行身份不一致" in r.stdout


def test_repair_fixes_mislabel_defaulted_news(db, tmp_path, monkeypatch):
    """Codex P1-7：被默认值顶替的错标（文件=文献、库=news）必须可修。

    旧执行逻辑用「库值 in VALID_TYPES」判幂等会把合法但错误的 news 跳过——
    dry-run 说可修、执行却 0 条。新逻辑以「回读文件重算值 ≠ 库值」为准，
    条件 UPDATE 匹配规划期 old_type，并发改动自动跳过。
    """
    db2 = db
    upload, recs = _import_and_corrupt(
        db2, tmp_path, monkeypatch, corrupt_values=("news", "news", "news"))
    # 3 行库值全 news；文件里只有第 2 行是「文献」→ 1 条错标应修成 literature
    r = _run_script("--dry-run")
    assert r.returncode == 0
    assert "可修复：1" in r.stdout
    assert "-> literature" in r.stdout

    backup = tmp_path / "bk2.json"
    r = _run_script("--backup", str(backup))
    assert r.returncode == 0
    assert "修复完成：1" in r.stdout
    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert payload["executed"] == 1
    assert payload["entries"][0].get("actual_old_type") == "news"
    db2.expire_all()
    recs = sorted(
        db2.scalars(
            __import__("sqlalchemy").select(BreadthManualRecord).where(
                BreadthManualRecord.upload_id == upload.id)
        ).all(),
        key=lambda r: r.title,
    )
    types = {r.title: r.intelligence_type for r in recs}
    assert types["钙钛矿叠层效率"] == "news"      # 文件=新闻，保持
    assert types["固态电池界面"] == "literature"  # 文件=文献，被修复
    assert types["电解质进展"] == "news"

    # 再跑一次：全部一致 → 幂等 no-op
    r = _run_script("--dry-run")
    assert "可修复：0" in r.stdout

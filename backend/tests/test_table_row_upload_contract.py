"""Contracts for Excel/CSV row import and breadth synchronization."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend" / "app" / "routers" / "uploads.py").read_text(encoding="utf-8")
ROWS = (ROOT / "backend" / "app" / "services" / "table_rows.py").read_text(encoding="utf-8")
PORTAL = (ROOT / "app.js").read_text(encoding="utf-8")


def test_row_mode_has_no_file_date_fallback():
    assert "fallback_date=None" in ROUTER
    assert "行日期不再用文件日期静默兜底" in ROUTER


def test_breadth_other_rows_are_visible_without_sync_checkbox():
    assert '(section == "breadth" and bsource == "other")' in ROUTER
    assert "row_in_breadth_nav" in ROUTER


def test_industry_atsc_sync_choice_is_persisted_and_controls_nav_visibility():
    assert "sync_breadth=sync_upload_to_breadth" in ROUTER
    assert 'sync_upload_to_breadth and section in ("industry", "atsc")' in ROUTER


def test_row_provenance_contains_file_sheet_and_row():
    assert 'source_ref={"file": source_file, "sheet": sheet_name, "row": row_no}' in ROWS


def test_row_mode_ui_disables_file_level_date_and_exposes_two_modes():
    assert "每行一个情报" in PORTAL
    assert "整个文件一个情报" in PORTAL
    assert "逐行模式：日期取自每行的日期列，无需文件级日期" in PORTAL
    assert "fieldset ${rowLocked?'disabled'" in PORTAL

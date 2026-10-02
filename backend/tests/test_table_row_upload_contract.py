"""Contracts for Excel/CSV row import and breadth synchronization."""
from pathlib import Path

import pytest

# G13（2026-10-02）：parents[2] 在容器内（/app/tests）解析为 /。改为沿父目录
# 回退查找：后端源码在容器内位于 /app/app（镜像内）、检出内位于
# <root>/backend/app；app.js 只存在于检出（api 镜像不含前端）。后端源码
# 缺失才模块级跳过；app.js 缺失仅跳过 UI 契约那一条。

_PARENTS = list(Path(__file__).resolve().parents)
_ROOT = _PARENTS[2] if len(_PARENTS) > 2 else _PARENTS[-1]


def _read_src(*candidates: Path) -> str:
    for c in candidates:
        try:
            return c.read_text(encoding="utf-8")
        except OSError:
            continue
    pytest.skip(
        f"contract source unavailable: {[str(c) for c in candidates]}",
        allow_module_level=True)


ROUTER = _read_src(_ROOT / "backend" / "app" / "routers" / "uploads.py",
                   *(_P / "app" / "routers" / "uploads.py" for _P in _PARENTS))
ROWS = _read_src(_ROOT / "backend" / "app" / "services" / "table_rows.py",
                 *(_P / "app" / "services" / "table_rows.py" for _P in _PARENTS))
try:
    PORTAL = (_ROOT / "app.js").read_text(encoding="utf-8")
except OSError:
    PORTAL = None


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


@pytest.mark.skipif(PORTAL is None,
                    reason="app.js 不在 api 镜像内（前端契约需检出环境）")
def test_row_mode_ui_disables_file_level_date_and_exposes_two_modes():
    assert "每行一个情报" in PORTAL
    assert "整个文件一个情报" in PORTAL
    assert "逐行模式：日期取自每行的日期列，无需文件级日期" in PORTAL
    assert "fieldset ${rowLocked?'disabled'" in PORTAL

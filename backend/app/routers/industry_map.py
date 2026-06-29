from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user

router = APIRouter(
    tags=["industry-map"],
    dependencies=[Depends(get_current_user)],
)

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "industry_map.json"


@router.get("/industry-map")
def get_industry_map(group: str | None = Query(default=None)) -> dict[str, Any]:
    if not DATA_PATH.exists():
        raise HTTPException(status_code=404, detail="industry_map_not_found")
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="industry_map_invalid_json") from exc
    sheets = data.get("sheets") or []
    if group:
        sheet = next((item for item in sheets if item.get("id") == group or item.get("title") == group), None)
        if sheet is None:
            raise HTTPException(status_code=404, detail="industry_sheet_not_found")
        return {"source": data.get("source"), "sheet_count": data.get("sheet_count", len(sheets)), "sheet": sheet, "sheets": sheets}
    return data

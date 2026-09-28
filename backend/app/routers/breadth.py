"""其他广度情报：真实入表的持久记录读写。

读取层契约：/api/breadth/manual-records 返回的记录同时带
- 长键字段（title/date/category/level/...）供管理界面使用；
- 短键字段（t/d/c/lv/aip/...）与广度总表 meta 分片逐字对齐，
  便于前端把人工记录合并进只读上游记录流。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.uploaded_file import UploadedFile

router = APIRouter(tags=["breadth"], dependencies=[Depends(get_current_user)])

# 人工等级：0 不设置；1 精选 ⊇ 2 重点 ⊇ 3 预警（沿用旧 tech-db 判断 level>=N）
LEVEL_RANGE = (0, 3)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _serialize(record: BreadthManualRecord) -> dict:
    return {
        "id": str(record.id),
        "record_id": str(record.id),
        "upload_id": str(record.upload_id),
        "user_id": record.user_id,
        "title": record.title,
        "body": record.body,
        "category": record.category or "未分类",
        "document_date": record.document_date,
        "level": int(record.level or 0),
        "intelligence_type": record.intelligence_type,
        "source_name": record.source_name,
        "url": record.url,
        "key_parameters": record.key_parameters or [],
        "ai_summary": record.ai_summary,
        "created_at": _iso(record.created_at),
        "updated_at": _iso(record.updated_at),
        # 广度总表短键（与 meta-part 记录字段逐字对齐）
        "t": record.title,
        "d": record.document_date or "",
        "c": record.category or "未分类",
        "lv": int(record.level or 0),
        "a": record.source_name or "",
        "i": "l" if record.intelligence_type in ("literature", "l") else "n",
        "u": record.url or "",
        "tg": "",
        "tp": "",
        "sc": record.score if record.score is not None else 0,
        "scd": record.score_detail or {},
        "aip": 0,
        "kp": record.key_parameters or [],
        "cm": "",
        "wr": "",
        "hb": 1,
        "source": "manual-import",
    }


class LevelPayload(BaseModel):
    level: int = Field(ge=0, le=3)


@router.get("/breadth/manual-records")
def list_manual_records(
    level: int | None = Query(default=None, ge=0, le=3),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(BreadthManualRecord).order_by(
        BreadthManualRecord.created_at.desc(), BreadthManualRecord.id.desc()
    )
    if level is not None:
        stmt = stmt.where(BreadthManualRecord.level == level)
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(BreadthManualRecord)) or 0
    level_counts: dict[str, int] = {}
    all_rows = db.scalars(select(BreadthManualRecord.level)).all()
    level_counts = {
        "curated": sum(1 for lv in all_rows if lv >= 1),
        "key": sum(1 for lv in all_rows if lv >= 2),
        "alert": sum(1 for lv in all_rows if lv >= 3),
        "zero": sum(1 for lv in all_rows if lv == 0),
    }
    return {
        "count": total,
        "records": [_serialize(r) for r in rows],
        "level_counts": level_counts,
    }


@router.get("/breadth/manual-records/{record_id}")
def get_manual_record(
    record_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(BreadthManualRecord, _uuid(record_id))
    if record is None:
        raise HTTPException(404, "广度记录不存在")
    return _serialize(record)


def _uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(400, "无效的记录 ID") from exc


class ManualUpdatePayload(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    level: int | None = Field(default=None, ge=0, le=3)
    category: str | None = Field(default=None, max_length=500)
    document_date: str | None = Field(default=None, max_length=32)


@router.patch("/breadth/manual-records/{record_id}")
def update_manual_record(
    record_id: str,
    payload: ManualUpdatePayload,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """改名/改分类/改人工等级：资料库生命周期同步的读侧入口。"""
    record = db.get(BreadthManualRecord, _uuid(record_id))
    if record is None:
        raise HTTPException(404, "广度记录不存在")
    if payload.title is not None:
        record.title = payload.title.strip()
    if payload.level is not None:
        record.level = payload.level
    if payload.category is not None:
        record.category = payload.category.strip() or None
    if payload.document_date is not None:
        record.document_date = payload.document_date.strip() or None
    # 同步上传资料标题（人工改名不可被 AI 覆盖：title_source 保持 manual）
    if payload.title is not None:
        upload = db.get(UploadedFile, record.upload_id)
        if upload is not None and upload.title_source == "manual":
            upload.title = record.title
    db.commit()
    db.refresh(record)
    return _serialize(record)

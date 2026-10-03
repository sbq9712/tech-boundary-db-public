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
    # record_json（feed v2 白名单全量）优先透出短键：包往返不丢字段
    # （cl/cp/cln/dp/hb/wr/sc/scd/tg/tp/aip…）；无 record_json 的行按列回退。
    rj = record.record_json if isinstance(record.record_json, dict) else {}

    def _rj(key: str, fallback):
        value = rj.get(key)
        return fallback if value is None else value

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
        "tag": record.tag,
        "topic": record.topic,
        "ai_picked": bool(record.ai_picked),
        "source_ref": record.source_ref,
        "in_breadth_nav": bool(record.in_breadth_nav),
        # 行业/ATSC「同步上传到广度」的行记录归属原栏目（spec-3tasks：
        # 同步仅是展示入口）——门户广度页展示该组记录时需要此字段。
        "origin_section": record.origin_section,
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
        "tg": record.tag or "",
        "tp": record.topic or "",
        "sc": record.score if record.score is not None else _rj("sc", 0),
        "scd": record.score_detail or _rj("scd", {}),
        "aip": 1 if record.ai_picked else 0,
        "kp": record.key_parameters or _rj("kp", []),
        "as": record.ai_summary or "",
        "cm": "",
        "wr": _rj("wr", ""),
        "hb": _rj("hb", 1),
        "cl": _rj("cl", None), "cp": _rj("cp", []), "cln": _rj("cln", None), "dp": _rj("dp", None),
        "source": "manual-import",
    }


class LevelPayload(BaseModel):
    level: int = Field(ge=0, le=3)


@router.get("/breadth/manual-records")
def list_manual_records(
    level: int | None = Query(default=None, ge=0, le=3),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    # 三.1：nav=仅主导航广度列表（默认，隐藏行业/ATSC 未勾选同步的行记录）；
    # all=资料库管理全量（含 in_breadth_nav=false 的行记录）。
    visibility: Literal["nav", "all"] = Query(default="nav"),
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(BreadthManualRecord).order_by(
        BreadthManualRecord.created_at.desc(), BreadthManualRecord.id.desc()
    )
    if visibility == "nav":
        stmt = stmt.where(BreadthManualRecord.in_breadth_nav)  # 主导航默认过滤
    if level is not None:
        stmt = stmt.where(BreadthManualRecord.level == level)
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    count_stmt = select(func.count()).select_from(BreadthManualRecord)
    if visibility == "nav":
        count_stmt = count_stmt.where(BreadthManualRecord.in_breadth_nav)
    total = db.scalar(count_stmt) or 0
    lv_stmt = select(BreadthManualRecord.level)
    if visibility == "nav":
        lv_stmt = lv_stmt.where(BreadthManualRecord.in_breadth_nav)
    all_rows = db.scalars(lv_stmt).all()
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
    # 问答索引跟随改名：重排队列里的 upsert 任务（worker 回读记录重建载荷）
    from app.services.breadth_index_queue import enqueue_record_upserts

    enqueue_record_upserts(db, [record])
    db.commit()
    return _serialize(record)

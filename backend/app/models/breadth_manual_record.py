from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BreadthManualRecord(Base):
    """其他广度情报的真实持久层：一个上传文件对应一条广度总表记录。

    - 与 uploaded_files 一对一（upload_id 唯一），上传删除级联删除；
    - 读取层把本表合并进广度总表（read-only 上游分片之上），等级沿用
      人工等级包含关系：lv>=1 精选 ⊇ lv>=2 重点 ⊇ lv>=3 预警；
    - content_hash 用于幂等：同一文件重复处理不会重复入表。
    """

    __tablename__ = "breadth_manual_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 人工情报等级：0 不设置 / 1 精选 / 2 重点 / 3 预警（包含关系）
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # news | literature
    intelligence_type: Mapped[str] = mapped_column(String(20), nullable=False, default="news")
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    key_parameters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

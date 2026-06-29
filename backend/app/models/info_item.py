from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InfoItem(Base):
    __tablename__ = "info_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_new_tech: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    info_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
    draft_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    alert_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alert_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alert_manual_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alert_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    alert_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_dismiss_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alert_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_modified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    domains: Mapped[list["InfoItemDomain"]] = relationship(
        "InfoItemDomain", back_populates="info_item", cascade="all, delete-orphan"
    )


class InfoItemDomain(Base):
    __tablename__ = "info_item_domains"

    info_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("info_items.id", ondelete="CASCADE"), primary_key=True
    )
    domain_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("domains.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    info_item: Mapped["InfoItem"] = relationship("InfoItem", back_populates="domains")

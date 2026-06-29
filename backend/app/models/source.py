from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stable_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # SRC-YYYYMMDD-XXXX or original src_ prefix from chatbot_integration_package
    external_ref: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # journal_rss | news_rss | wechat | pdf | webpage | report | patent | interview | colleague_submission | paid_db
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    url_or_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(500), nullable=True)  # journal / website name
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    access_level: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    # public | internal | restricted | paid
    local_snapshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    reliability_rating: Mapped[str] = mapped_column(String(20), nullable=False, default="unrated")
    # high | medium | low | unrated

    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subdomain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    needs_reclassification: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    evidence: Mapped[list["Evidence"]] = relationship("Evidence", back_populates="source", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stable_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # EVD-YYYYMMDD-XXXX

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    quote_or_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_or_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    extracted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    # high | medium | low
    local_asset_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    source: Mapped["Source"] = relationship("Source", back_populates="evidence")

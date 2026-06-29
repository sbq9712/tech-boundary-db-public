from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Numeric, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ParameterObservation(Base):
    __tablename__ = "parameter_observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stable_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # OBS-YYYYMMDD-XXXX

    intelligence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("info_items.id", ondelete="SET NULL"), nullable=True, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True)
    technology_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # TECH-XXXX stable ID

    parameter_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    parameter_type: Mapped[str] = mapped_column(String(30), nullable=False, default="technical")
    # technical | economic | industrial | commercial

    value_min: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    value_max: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    condition_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor_or_company: Mapped[str | None] = mapped_column(String(200), nullable=True)

    extraction_confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    # high | medium | low
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False, default="machine_extracted")
    # machine_extracted | human_checked | disputed | rejected | superseded

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

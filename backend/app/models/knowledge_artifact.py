from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeArtifact(Base):
    __tablename__ = "knowledge_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stable_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # ART-YYYYMMDD-XXXX

    artifact_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # data_anchor | broad_knowledge_note | deep_research_note | industry_dashboard | special_report | ppt_deliverable | decision_record
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    vault_path: Mapped[str | None] = mapped_column(Text, nullable=True)   # Obsidian vault 相对路径
    absolute_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    related_tech_node_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_ind_node_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_intelligence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    related_observation_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

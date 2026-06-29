from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TechnologyNode(Base):
    __tablename__ = "technology_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # TECH-XXXX stable ID
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("technology_nodes.id", ondelete="SET NULL"), nullable=True)
    node_type: Mapped[str] = mapped_column(String(30), nullable=False, default="route")
    # route | material | component | parameter | mechanism | common_tech | bottleneck
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class IndustryNode(Base):
    __tablename__ = "industry_nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # IND-XXXX stable ID
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("industry_nodes.id", ondelete="SET NULL"), nullable=True)
    node_type: Mapped[str] = mapped_column(String(30), nullable=False, default="scenario")
    # scenario | company | project | supply_chain | policy | business_model
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TechIndustryRelation(Base):
    __tablename__ = "tech_industry_relations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_node_type: Mapped[str] = mapped_column(String(10), nullable=False)  # tech | ind
    from_node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    to_node_type: Mapped[str] = mapped_column(String(10), nullable=False)
    to_node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # applies_to | depends_on | competes_with | supplies | collaborates_with
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InfoItemTechNode(Base):
    __tablename__ = "info_item_tech_nodes"

    info_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("info_items.id", ondelete="CASCADE"), primary_key=True)
    tech_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("technology_nodes.id", ondelete="CASCADE"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False)


class InfoItemIndNode(Base):
    __tablename__ = "info_item_ind_nodes"

    info_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("info_items.id", ondelete="CASCADE"), primary_key=True)
    ind_node_id: Mapped[str] = mapped_column(String(64), ForeignKey("industry_nodes.id", ondelete="CASCADE"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False)

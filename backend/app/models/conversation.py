from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.username", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topic_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    messages: Mapped[list["ConversationMessage"]] = relationship("ConversationMessage", back_populates="session", cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    panel_recommendations_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session: Mapped["ConversationSession"] = relationship("ConversationSession", back_populates="messages")


class UserResearchProfile(Base):
    __tablename__ = "user_research_profiles"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.username", ondelete="CASCADE"), primary_key=True)
    preferred_domains: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_depth: Mapped[str] = mapped_column(String(20), nullable=False, default="balanced")
    # quick | balanced | deep
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="zh")
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UserResearchMemory(Base):
    __tablename__ = "user_research_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.username", ondelete="CASCADE"), nullable=False, index=True)
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # verified_fact | assumption | missing_data | decision | source_anchor
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

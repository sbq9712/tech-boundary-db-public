from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.conversation import (
    ConversationMessage,
    ConversationSession,
    UserResearchMemory,
    UserResearchProfile,
)

router = APIRouter(tags=["conversations"], dependencies=[Depends(get_current_user)])


class SessionIn(BaseModel):
    title: str | None = None
    topic_hint: str | None = None


class MessageIn(BaseModel):
    role: str  # user | assistant
    content: str
    citations_json: list = []
    panel_recommendations_json: dict = {}


class MemoryIn(BaseModel):
    topic: str | None = None
    kind: str  # verified_fact | assumption | missing_data | decision | source_anchor
    content: str
    source_ref: str | None = None
    confidence: str = "medium"


# ── Sessions ──────────────────────────────────────────────

@router.get("/conversations")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    rows = db.scalars(
        select(ConversationSession)
        .where(ConversationSession.user_id == current_user)
        .order_by(ConversationSession.updated_at.desc())
        .limit(50)
    ).all()
    return {"sessions": [{"id": str(s.id), "title": s.title, "topic_hint": s.topic_hint, "updated_at": s.updated_at.isoformat()} for s in rows]}


@router.post("/conversations", status_code=201)
def create_session(
    payload: SessionIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    s = ConversationSession(id=uuid.uuid4(), user_id=current_user, **payload.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": str(s.id), "title": s.title, "topic_hint": s.topic_hint}


# ── Messages ──────────────────────────────────────────────

@router.get("/conversations/{session_id}/messages")
def get_messages(
    session_id: UUID,
    limit: int = 40,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    s = db.get(ConversationSession, session_id)
    if not s or s.user_id != current_user:
        raise HTTPException(404, "session not found")
    msgs = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc())
        .limit(limit)
    ).all()
    return {"session_id": str(session_id), "messages": [
        {"id": str(m.id), "role": m.role, "content": m.content,
         "citations": m.citations_json, "panel_recommendations": m.panel_recommendations_json,
         "created_at": m.created_at.isoformat()} for m in msgs
    ]}


@router.post("/conversations/{session_id}/messages", status_code=201)
def add_message(
    session_id: UUID,
    payload: MessageIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    s = db.get(ConversationSession, session_id)
    if not s or s.user_id != current_user:
        raise HTTPException(404, "session not found")
    msg = ConversationMessage(id=uuid.uuid4(), session_id=session_id, **payload.model_dump())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"id": str(msg.id), "role": msg.role, "created_at": msg.created_at.isoformat()}


# ── User Memory ───────────────────────────────────────────

@router.get("/user-memory")
def get_memory(
    topic: str | None = None,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    stmt = select(UserResearchMemory).where(UserResearchMemory.user_id == current_user)
    if topic:
        stmt = stmt.where(UserResearchMemory.topic == topic)
    stmt = stmt.order_by(UserResearchMemory.updated_at.desc()).limit(100)
    items = db.scalars(stmt).all()
    return {"items": [{"id": str(m.id), "topic": m.topic, "kind": m.kind, "content": m.content, "confidence": m.confidence, "source_ref": m.source_ref, "created_at": m.created_at.isoformat()} for m in items]}


@router.post("/user-memory", status_code=201)
def add_memory(
    payload: MemoryIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    item = UserResearchMemory(id=uuid.uuid4(), user_id=current_user, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": str(item.id), "kind": item.kind, "created_at": item.created_at.isoformat()}


# ── User Profile ──────────────────────────────────────────

@router.get("/user-profile")
def get_profile(
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    p = db.get(UserResearchProfile, current_user)
    if not p:
        return {"user_id": current_user, "preferred_domains": [], "preferred_depth": "balanced", "language": "zh", "role": None}
    return {"user_id": p.user_id, "preferred_domains": p.preferred_domains, "preferred_depth": p.preferred_depth, "language": p.language, "role": p.role}

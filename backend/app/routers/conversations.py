from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
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
    citations_json: list = Field(default_factory=list)
    panel_recommendations_json: dict = Field(default_factory=dict)
    retrieval_summary_json: dict = Field(default_factory=dict)


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


@router.delete("/conversations/{session_id}", status_code=204)
def delete_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> Response:
    session = db.get(ConversationSession, session_id)
    if not session or session.user_id != current_user:
        raise HTTPException(404, "session not found")
    db.delete(session)
    db.commit()
    return Response(status_code=204)


# ── Messages ──────────────────────────────────────────────


def _message_retrieval_summary(message: ConversationMessage) -> dict:
    if message.retrieval_summary_json:
        return message.retrieval_summary_json
    citations = message.citations_json or []
    return {
        "knowledge_base": sum(1 for item in citations if item.get("type") == "knowledge_base"),
        "sources": sum(1 for item in citations if item.get("type") == "source"),
        "parameters": sum(1 for item in citations if item.get("type") == "parameter"),
        "derived_from_citations": True,
    }

@router.get("/conversations/{session_id}/messages")
def get_messages(
    session_id: UUID,
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    s = db.get(ConversationSession, session_id)
    if not s or s.user_id != current_user:
        raise HTTPException(404, "session not found")
    newest_first = db.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(limit)
    ).all()
    msgs = list(reversed(newest_first))
    return {"session_id": str(session_id), "messages": [
        {"id": str(m.id), "role": m.role, "content": m.content,
         "citations": m.citations_json, "panel_recommendations": m.panel_recommendations_json,
         "retrieval_summary": _message_retrieval_summary(m),
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

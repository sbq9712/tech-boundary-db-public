from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.conversation import ConversationSession
from app.services.agent_service import get_available_models, resolve_model, stream_agent_response

router = APIRouter(tags=["assistant-stream"], dependencies=[Depends(get_current_user)])


class StreamQueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    session_id: uuid.UUID | None = None
    model: str | None = Field(default=None, max_length=80)
    regenerate: bool = False
    retry: bool = False


def _conversation_title(query: str) -> str:
    text = query.strip()
    return text[:20] + ("..." if len(text) > 20 else "")


def _resolve_session(
    db: Session,
    current_user: str,
    session_id: uuid.UUID | None,
    query: str,
) -> ConversationSession:
    if session_id:
        session = db.get(ConversationSession, session_id)
        if not session or session.user_id != current_user:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    session = ConversationSession(
        id=uuid.uuid4(),
        user_id=current_user,
        title=_conversation_title(query),
        topic_hint=query.strip()[:200],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _stream_response(
    payload: StreamQueryIn,
    db: Session,
    current_user: str,
) -> StreamingResponse:
    try:
        selected_model = resolve_model(payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session = _resolve_session(db, current_user, payload.session_id, payload.query)
    return StreamingResponse(
        stream_agent_response(
            payload.query,
            str(session.id),
            db,
            selected_model=selected_model,
            current_user=current_user,
            regenerate=payload.regenerate,
            retry=payload.retry,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": str(session.id),
        },
    )


@router.get("/assistant/models")
def assistant_models() -> dict:
    """Return the model choices available in the portal selector."""
    return get_available_models()


@router.get("/assistant/stream")
async def stream_query(
    query: str = Query(..., min_length=1, max_length=2000),
    session_id: str | None = None,
    model: str | None = Query(default=None, max_length=80),
    regenerate: bool = False,
    retry: bool = False,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """
    Stream agent response via Server-Sent Events (SSE).
    
    Returns SSE event stream:
    - event: status, data: {"stage": "retrieving|analyzing|generating", "message": "..."}
    - event: token, data: {"content": "token text"}
    - event: done, data: {"response": "...", "citations": [...], "session_id": "..."}
    
    Usage:
        const es = new EventSource('/api/assistant/stream?query=xxx');
        es.addEventListener('status', (e) => console.log('Status:', JSON.parse(e.data)));
        es.addEventListener('token', (e) => console.log('Token:', JSON.parse(e.data).content));
        es.addEventListener('done', (e) => { console.log('Done:', JSON.parse(e.data)); es.close(); });
    """
    parsed_session_id = None
    if session_id:
        try:
            parsed_session_id = uuid.UUID(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid session_id") from exc
    return _stream_response(
        StreamQueryIn(query=query, session_id=parsed_session_id, model=model, regenerate=regenerate, retry=retry),
        db,
        current_user,
    )


@router.post("/assistant/stream")
async def stream_query_post(
    payload: StreamQueryIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Stream a persisted, user-scoped conversation without putting the query in the URL."""
    return _stream_response(payload, db, current_user)

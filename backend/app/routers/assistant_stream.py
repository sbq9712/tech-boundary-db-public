from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.services.agent_service import stream_agent_response

router = APIRouter(tags=["assistant-stream"], dependencies=[Depends(get_current_user)])


@router.get("/assistant/stream")
async def stream_query(
    query: str = Query(..., min_length=1, max_length=2000),
    session_id: str | None = None,
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
    return StreamingResponse(
        stream_agent_response(query, session_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )

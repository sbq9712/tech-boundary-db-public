from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services.github_qa import QAServiceError, graph_snapshot, service_status
from app.services.hermes_bridge import HermesAgentBridge

router = APIRouter(
    tags=["assistant"],
    dependencies=[Depends(get_current_user)],
)


class AssistantQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    context: str | None = Field(default=None, max_length=200)


@router.get("/assistant/status")
async def assistant_status() -> dict:
    return await service_status()


@router.get("/assistant/graph")
async def assistant_graph(limit: int = Query(default=200, ge=1, le=500)) -> dict:
    try:
        return await graph_snapshot(limit)
    except QAServiceError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": exc.public_message}) from exc


@router.post("/assistant/query")
def submit_assistant_query(payload: AssistantQuery) -> dict:
    bridge = HermesAgentBridge()
    return bridge.ask(payload.query, payload.context or "portal").to_dict()

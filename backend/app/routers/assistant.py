from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.services.hermes_bridge import HermesAgentBridge
from urllib import request as urlrequest
from urllib.error import URLError
import json
import os

router = APIRouter(
    tags=["assistant"],
    dependencies=[Depends(get_current_user)],
)


class AssistantQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    context: str | None = Field(default=None, max_length=200)


@router.get("/assistant/status")
def assistant_status() -> dict:
    mode = os.getenv("HERMES_AGENT_MODE", "mock").strip().lower()
    query_url = os.getenv("HERMES_AGENT_HTTP_URL", "").strip()
    health_url = query_url.rsplit("/", 1)[0] + "/health" if query_url else ""
    payload = {"status": "configured", "mode": mode, "agent": None, "health": None}
    if mode != "http" or not health_url:
        return payload
    try:
        with urlrequest.urlopen(health_url, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        payload.update({"status": "error", "error": str(exc)})
        return payload
    payload.update({"status": "ok", "agent": body.get("agent"), "health": body})
    return payload


@router.post("/assistant/query")
def submit_assistant_query(payload: AssistantQuery) -> dict:
    bridge = HermesAgentBridge()
    return bridge.ask(payload.query, payload.context or "portal").to_dict()

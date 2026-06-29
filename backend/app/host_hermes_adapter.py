from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="TechDB Hermes Adapter", version="0.1.0")

HERMES_CLI = os.getenv("HERMES_CLI", "hermes")
HERMES_TIMEOUT_SECONDS = int(os.getenv("HERMES_TIMEOUT_SECONDS", "180"))
HERMES_TOOLSETS = os.getenv("HERMES_TOOLSETS", "").strip()


class QueryIn(BaseModel):
    query: str = Field(..., min_length=1)
    context: str | None = None


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "agent": "host-hermes",
        "mode": "cli-wrapper",
        "hermes_cli": HERMES_CLI,
        "toolsets": HERMES_TOOLSETS,
    }


@app.post("/query")
def query(payload: QueryIn) -> dict:
    prompt = (
        "你是技术边界数据库门户的问答 Agent。"
        "请直接回答用户问题；如果需要证据但当前上下文不足，明确说明需要查询哪些知识库或数据。"
        "不要声称已经读取未提供的文件或数据库。\n\n"
        f"上下文: {payload.context or 'portal'}\n"
        f"用户问题: {payload.query.strip()}"
    )
    cmd = [HERMES_CLI, "-z", prompt]
    if HERMES_TOOLSETS:
        cmd.extend(["-t", HERMES_TOOLSETS])
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=HERMES_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"answer": "Hermes 调用超时。", "agent": "host-hermes", "ai_error": "timeout"}
    except OSError as exc:
        return {"answer": "无法启动宿主 Hermes CLI。", "agent": "host-hermes", "ai_error": str(exc)}
    if completed.returncode != 0:
        return {
            "answer": completed.stdout.strip() or "Hermes CLI 返回错误。",
            "agent": "host-hermes",
            "ai_error": completed.stderr.strip() or f"exit_code={completed.returncode}",
        }
    return {
        "answer": completed.stdout.strip(),
        "agent": "host-hermes",
        "ai_error": None,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "panel_recommendations": {
            "hot_intel": [],
            "parameter_boundaries": [],
            "alert_intel": [],
            "dashboard_links": [],
        },
    }

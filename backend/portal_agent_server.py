from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

HOST = os.getenv("TECHDB_AGENT_HOST", "0.0.0.0")
PORT = int(os.getenv("TECHDB_AGENT_PORT", "8766"))
STATE_FILE = Path(os.getenv("TECHDB_AGENT_STATE_FILE", "/tmp/techdb_portal_agent_state.json"))
API_KEY = os.getenv("TECHDB_AGENT_API_KEY", "").strip()
BASE_URL = os.getenv("TECHDB_AGENT_BASE_URL", "https://aigate.catl.com/v1").rstrip("/")
MODEL = os.getenv("TECHDB_AGENT_MODEL", "GLM-5.2")
TIMEOUT_SECONDS = int(os.getenv("TECHDB_AGENT_AI_TIMEOUT_SECONDS", "180"))
MAX_HISTORY_MESSAGES = int(os.getenv("TECHDB_AGENT_MAX_HISTORY_MESSAGES", "16"))
MAX_TOKENS = int(os.getenv("TECHDB_AGENT_MAX_TOKENS", "1200"))
TEMPERATURE = float(os.getenv("TECHDB_AGENT_TEMPERATURE", "0.2"))

SYSTEM_PROMPT = (
    "你是技术边界数据库门户的常驻问答 Agent。"
    "面向能源/清洁技术咨询、技术尽调和行业研究场景回答。"
    "回答应直接、审慎、区分已验证事实/推测/缺失数据。"
    "如果当前对话没有提供证据或知识库检索结果，必须明确说明不能核实，不要假装已读取数据库或文件。"
    "当用户请求继续分析时，应利用本会话已有上下文。"
)

state: dict[str, Any] = {"messages": [], "created_at": datetime.now(timezone.utc).isoformat()}


def load_state() -> None:
    global state
    try:
        loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("messages"), list):
            state = loaded
    except (OSError, json.JSONDecodeError):
        save_state()


def save_state() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def trim_messages() -> None:
    messages = state.get("messages", [])
    if len(messages) > MAX_HISTORY_MESSAGES:
        state["messages"] = messages[-MAX_HISTORY_MESSAGES:]


def call_model() -> tuple[str, str | None]:
    if not API_KEY:
        return "", "missing_api_key"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + [
        {"role": item["role"], "content": item["content"]}
        for item in state.get("messages", [])
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }
    req = urlrequest.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return "", f"http_{exc.code}: {detail}"
    except (URLError, TimeoutError, OSError) as exc:
        return "", f"request_failed: {exc.__class__.__name__}"
    try:
        return body["choices"][0]["message"]["content"].strip(), None
    except (KeyError, IndexError, TypeError):
        return "", "response_parse_failed"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(
                self,
                {
                    "status": "ok",
                    "agent": "techdb-resident-agent",
                    "mode": "resident-openai-compatible",
                    "model": MODEL,
                    "ai_enabled": bool(API_KEY),
                    "message_count": len(state.get("messages", [])),
                    "state_file": str(STATE_FILE),
                },
            )
            return
        json_response(self, {"error": "not_found"}, 404)

    def do_POST(self) -> None:
        if self.path == "/reset":
            state["messages"] = []
            state["reset_at"] = datetime.now(timezone.utc).isoformat()
            save_state()
            json_response(self, {"status": "ok", "message_count": 0})
            return
        if self.path != "/query":
            json_response(self, {"error": "not_found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            query = str(payload.get("query", "")).strip()
            context = str(payload.get("context", "portal"))
        except Exception as exc:
            json_response(self, {"answer": "请求格式错误。", "agent": "techdb-resident-agent", "ai_error": str(exc)}, 400)
            return
        if not query:
            json_response(self, {"answer": "问题不能为空。", "agent": "techdb-resident-agent", "ai_error": "empty_query"}, 400)
            return
        state.setdefault("messages", []).append({"role": "user", "content": f"上下文: {context}\n用户问题: {query}", "ts": datetime.now(timezone.utc).isoformat()})
        trim_messages()
        started = time.perf_counter()
        answer, error = call_model()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if error:
            save_state()
            json_response(self, {"answer": "常驻 Agent 调用模型失败。", "agent": "techdb-resident-agent", "ai_error": error, "elapsed_ms": elapsed_ms, "message_count": len(state.get("messages", []))})
            return
        state.setdefault("messages", []).append({"role": "assistant", "content": answer, "ts": datetime.now(timezone.utc).isoformat()})
        trim_messages()
        save_state()
        json_response(
            self,
            {
                "answer": answer,
                "agent": "techdb-resident-agent",
                "ai_error": None,
                "elapsed_ms": elapsed_ms,
                "message_count": len(state.get("messages", [])),
                "received_at": datetime.now(timezone.utc).isoformat(),
                "panel_recommendations": {"hot_intel": [], "parameter_boundaries": [], "alert_intel": [], "dashboard_links": []},
            },
        )


if __name__ == "__main__":
    load_state()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

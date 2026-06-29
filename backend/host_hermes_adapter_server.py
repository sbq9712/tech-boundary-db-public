from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.getenv("HERMES_ADAPTER_HOST", "0.0.0.0")
PORT = int(os.getenv("HERMES_ADAPTER_PORT", "8766"))
HERMES_CLI = os.getenv("HERMES_CLI", "hermes")
HERMES_TIMEOUT_SECONDS = int(os.getenv("HERMES_TIMEOUT_SECONDS", "180"))
HERMES_TOOLSETS = os.getenv("TECHDB_HERMES_TOOLSETS", "").strip()
SESSION_FILE = Path(os.getenv("TECHDB_HERMES_SESSION_FILE", "/tmp/techdb_portal_hermes_session.json"))
SESSION_SOURCE = os.getenv("TECHDB_HERMES_SESSION_SOURCE", "techdb-portal")


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_session_id() -> str | None:
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        value = str(data.get("session_id", "")).strip()
        return value or None
    except (OSError, json.JSONDecodeError):
        return None


def write_session_id(session_id: str) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(
        json.dumps({"session_id": session_id, "updated_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False),
        encoding="utf-8",
    )


def latest_session_id() -> str | None:
    try:
        completed = subprocess.run(
            [HERMES_CLI, "sessions", "list", "--source", SESSION_SOURCE, "--limit", "5"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        parts = line.split()
        if parts and parts[-1].startswith("20") and "_" in parts[-1]:
            return parts[-1]
    return None


def clean_answer(text: str) -> str:
    lines = [line for line in text.splitlines() if not line.startswith("Warning: Unknown toolsets:")]
    return "\n".join(lines).strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path != "/health":
            json_response(self, {"error": "not_found"}, 404)
            return
        json_response(
            self,
            {
                "status": "ok",
                "agent": "host-hermes",
                "mode": "cli-wrapper",
                "session_id": read_session_id(),
                "session_source": SESSION_SOURCE,
            },
        )

    def do_POST(self) -> None:
        if self.path != "/query":
            json_response(self, {"error": "not_found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            query = str(payload.get("query", "")).strip()
            context = str(payload.get("context", "portal"))
        except Exception as exc:
            json_response(self, {"answer": "请求格式错误。", "agent": "host-hermes", "ai_error": str(exc)}, 400)
            return
        prompt = (
            "你是技术边界数据库门户的问答 Agent。"
            "请直接回答用户问题；如果需要证据但当前上下文不足，明确说明需要查询哪些知识库或数据。"
            "不要声称已经读取未提供的文件或数据库。\n\n"
            f"上下文: {context}\n用户问题: {query}"
        )
        session_id = read_session_id()
        cmd = [HERMES_CLI, "chat", "-q", prompt, "--source", SESSION_SOURCE, "-Q", "--cli"]
        if session_id:
            cmd.extend(["--resume", session_id])
        if HERMES_TOOLSETS.strip():
            cmd.extend(["-t", HERMES_TOOLSETS.strip()])
        started = time.perf_counter()
        env = os.environ.copy()
        env.pop("HERMES_TOOLSETS", None)
        try:
            completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=HERMES_TIMEOUT_SECONDS, env=env)
        except subprocess.TimeoutExpired:
            json_response(self, {"answer": "Hermes 调用超时。", "agent": "host-hermes", "ai_error": "timeout", "session_id": session_id})
            return
        except OSError as exc:
            json_response(self, {"answer": "无法启动宿主 Hermes CLI。", "agent": "host-hermes", "ai_error": str(exc), "session_id": session_id})
            return
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if completed.returncode != 0:
            json_response(
                self,
                {
                    "answer": clean_answer(completed.stdout) or "Hermes CLI 返回错误。",
                    "agent": "host-hermes",
                    "ai_error": completed.stderr.strip() or f"exit_code={completed.returncode}",
                    "session_id": session_id,
                    "elapsed_ms": elapsed_ms,
                },
            )
            return
        current_session_id = session_id or latest_session_id()
        if current_session_id:
            write_session_id(current_session_id)
        json_response(
            self,
            {
                "answer": clean_answer(completed.stdout),
                "agent": "host-hermes",
                "ai_error": None,
                "received_at": datetime.now(timezone.utc).isoformat(),
                "session_id": current_session_id,
                "elapsed_ms": elapsed_ms,
                "panel_recommendations": {"hot_intel": [], "parameter_boundaries": [], "alert_intel": [], "dashboard_links": []},
            },
        )


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

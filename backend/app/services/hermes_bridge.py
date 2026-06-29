from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib import request as urlrequest
from urllib.error import URLError
import json


@dataclass(frozen=True)
class HermesAgentResult:
    status: str
    mode: str
    message: str
    query: str
    context: str
    received_at: str
    response: str | None = None
    error: str | None = None
    suggested_next_steps: list[str] | None = None
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "message": self.message,
            "query": self.query,
            "context": self.context,
            "received_at": self.received_at,
            "response": self.response,
            "error": self.error,
            "suggested_next_steps": self.suggested_next_steps or [],
            "extra": self.extra or {},
        }


class HermesAgentBridge:
    def __init__(self) -> None:
        self.mode = os.getenv("HERMES_AGENT_MODE", "cli").strip().lower()
        self.timeout = int(os.getenv("HERMES_AGENT_TIMEOUT_SECONDS", "45"))
        self.cli_path = os.getenv("HERMES_AGENT_CLI", "hermes")
        self.http_url = os.getenv("HERMES_AGENT_HTTP_URL", "").strip()
        self.toolsets = os.getenv("HERMES_AGENT_TOOLSETS", "").strip()

    def ask(self, query: str, context: str = "portal") -> HermesAgentResult:
        cleaned_query = query.strip()
        if not cleaned_query:
            return self._result("error", self.mode, "问题不能为空。", cleaned_query, context, error="empty_query")
        if self.mode == "cli":
            return self._ask_cli(cleaned_query, context)
        if self.mode == "http":
            return self._ask_http(cleaned_query, context)
        return self._ask_mock(cleaned_query, context)

    def _ask_mock(self, query: str, context: str) -> HermesAgentResult:
        return self._result(
            "placeholder_ready",
            "mock",
            "门户已接入 Hermes Agent Bridge，但当前运行在 mock 模式，尚未调用真实 Hermes agent。",
            query,
            context,
            response=None,
            suggested_next_steps=[
                "设置 HERMES_AGENT_MODE=cli 并确保后端运行环境可执行 hermes -z",
                "或设置 HERMES_AGENT_MODE=http 与 HERMES_AGENT_HTTP_URL 接入独立 agent 服务",
                "为生产环境增加权限边界、审计日志和知识库检索限制",
            ],
        )

    def _ask_cli(self, query: str, context: str) -> HermesAgentResult:
        prompt = self._build_prompt(query, context)
        cmd = [self.cli_path, "-z", prompt]
        if self.toolsets:
            cmd.extend(["-t", self.toolsets])
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return self._result("error", "cli", "Hermes agent 调用超时。", query, context, error="timeout")
        except OSError as exc:
            return self._result("error", "cli", "无法启动 Hermes CLI。", query, context, error=str(exc))

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if completed.returncode != 0:
            return self._result(
                "error",
                "cli",
                "Hermes CLI 返回错误。",
                query,
                context,
                response=stdout or None,
                error=stderr or f"exit_code={completed.returncode}",
            )
        return self._result("agent_connected", "cli", "Hermes agent 已返回结果。", query, context, response=stdout)

    def _ask_http(self, query: str, context: str) -> HermesAgentResult:
        if not self.http_url:
            return self._result("error", "http", "HERMES_AGENT_HTTP_URL 未配置。", query, context, error="missing_url")
        payload = json.dumps({"query": query, "context": context}).encode("utf-8")
        req = urlrequest.Request(
            self.http_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except URLError as exc:
            return self._result("error", "http", "Hermes HTTP agent 调用失败。", query, context, error=str(exc))
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"response": body}
        return self._result(
            "agent_connected",
            "http",
            "TechDB readonly agent 已返回结果。",
            query,
            context,
            response=parsed.get("answer") or parsed.get("response") or body,
            extra={key: value for key, value in parsed.items() if key not in {"answer", "response"}},
        )

    def _build_prompt(self, query: str, context: str) -> str:
        return (
            "你是技术边界数据库门户的受限问答 Agent。"
            "只回答用户提出的技术/数据库/项目问题；不要执行系统操作；"
            "如果缺少证据，明确说明尚未核实。\n\n"
            f"上下文: {context}\n用户问题: {query}"
        )

    def _result(
        self,
        status: str,
        mode: str,
        message: str,
        query: str,
        context: str,
        response: str | None = None,
        error: str | None = None,
        suggested_next_steps: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> HermesAgentResult:
        return HermesAgentResult(
            status=status,
            mode=mode,
            message=message,
            query=query,
            context=context,
            received_at=datetime.now(timezone.utc).isoformat(),
            response=response,
            error=error,
            suggested_next_steps=suggested_next_steps,
            extra=extra,
        )

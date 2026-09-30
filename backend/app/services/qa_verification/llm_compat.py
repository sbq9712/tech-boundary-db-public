"""qa_verification 的 LLM 桥（五.1，2026-09-30）。

旧仓库核验模块统一经 `config.llm_model_func(prompt, system_prompt=...,
max_tokens=...)` 调用 LLM。backend 侧没有那个 config——本桥用
agent_service 的模型网关配置（TECHDB_AGENT_*）实现同签名函数：
- 非流式 OpenAI 兼容 /chat/completions（httpx，复用 agent_service 的超时）；
- 模型取请求级 contextvar（stream_agent_response 为每次问答设定），
  未设定时回退 TECHDB_AGENT_MODEL；
- 任何失败向上抛异常——调用方（verifier/claim_mapping/epistemic）按
  FAIL_SAFE 契约自行降级，本桥不吞错。
"""
from __future__ import annotations

import contextvars
import json

import httpx

# 请求级模型（stream_agent_response 每次问答 set；核验 LLM 调用与生成同模型，
# 保证「冻结相同模型和配置」的可比性——五.4 前提）。
current_model: contextvars.ContextVar[str] = contextvars.ContextVar(
    "qa_verification_model", default="")


def _settings() -> tuple[str, str, str]:
    from app.services.agent_service import AI_API_KEY, AI_BASE_URL
    model = current_model.get() or __import__("os").environ.get("TECHDB_AGENT_MODEL", "")
    return AI_BASE_URL, AI_API_KEY, model


async def llm_model_func(prompt: str, system_prompt: str | None = None,
                         history_messages: list | None = None,
                         **kwargs) -> str:
    """旧 config.llm_model_func 的 backend 等价实现（非流式）。"""
    import asyncio
    import os

    base_url, api_key, model = _settings()
    if not api_key or not base_url or not model:
        raise RuntimeError(
            "qa_verification llm gateway not configured "
            "(TECHDB_AGENT_API_KEY/BASE_URL/MODEL)")
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": kwargs.get("temperature", 0.3),
        "max_tokens": kwargs.get("max_tokens", 4096),
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}

    timeout = float(os.environ.get("TECHDB_AGENT_AI_TIMEOUT_SECONDS", "180"))

    async def _do() -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}/chat/completions",
                                     json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if isinstance(content, list):
            content = "".join(p.get("text", "") if isinstance(p, dict) else str(p)
                              for p in content)
        return content

    return await asyncio.shield(_do())

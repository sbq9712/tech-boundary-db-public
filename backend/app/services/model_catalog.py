"""Credential-scoped model discovery; no vendor catalog or credential logging."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from urllib.parse import urlsplit

import httpx

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}


def get_catalog(base_url: str, api_key: str, default: str, configured: list[str], refresh: bool = False) -> dict:
    base_url = base_url.strip().rstrip("/")
    empty = {"models": [], "default_model": None, "source": "unavailable"}
    try:
        parts = urlsplit(base_url)
    except ValueError:
        return {**empty, "message": "请配置有效的服务 URL。"}
    if not api_key or parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        return {**empty, "message": "请配置当前环境的 API Key 和有效服务 URL。"}
    identity = hashlib.sha256(json.dumps([base_url, api_key, default, configured]).encode()).hexdigest()
    if not refresh:
        # refresh=True（「更新模型列表」按钮）绕过 60s 缓存直接请求上游，成功后回填缓存
        with _lock:
            cached = _cache.get(identity)
            if cached and cached[0] > time.monotonic():
                return dict(cached[1])
    models = []
    source = "discovered"
    message = "当前 API 返回的模型目录；具体调用权限以服务端响应为准。"
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", base_url + "/models", headers={"Authorization": "Bearer " + api_key}) as response:
                if response.status_code in {404, 405, 501}:
                    source = "configured"
                    models = list(dict.fromkeys(m.strip() for m in [*configured, default] if m.strip()))
                    message = "服务不支持模型目录；使用当前环境显式配置的模型，请确认账号权限。"
                else:
                    response.raise_for_status()
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            raise ValueError("catalog too large")
                    payload = json.loads(raw)
                    rows = payload.get("data") if isinstance(payload, dict) else None
                    if not isinstance(rows, list):
                        raise ValueError("invalid catalog")
                    for row in rows:
                        name = row.get("id") if isinstance(row, dict) else None
                        if isinstance(name, str) and name.strip() == name and name and len(name) <= 80 and name not in models:
                            models.append(name)
    except (httpx.HTTPError, ValueError):
        # Never expose upstream response bodies, URLs or credentials to clients.
        return {**empty, "message": "无法读取当前 API 的模型目录，请检查配置、授权和网络后刷新。"}
    selected = default if default in models else (models[0] if models else None)
    result = {"models": models, "default_model": selected, "source": source, "message": message}
    with _lock:
        if len(_cache) >= 32:
            _cache.clear()
        _cache[identity] = (time.monotonic() + 60, result)
    return dict(result)

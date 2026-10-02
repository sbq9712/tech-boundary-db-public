"""T8（2026-10-02）：TECHDB_QA_INDEX_TOKEN 写端点闸门单元测试。

沿用本目录「源码截取」约定（不导入完整 server.py 的 FastAPI 运行时依赖）：
从 server.py 截取 _PLACEHOLDER_TOKENS + _check_index_token，验证三种状态——
1) 未配置 / 占位符 → 503（带修复指引，服务端明确拒绝而非裸奔）；
2) 已配置但请求 token 不匹配 → 401；
3) 已配置且匹配（compare_digest）→ 放行。
"""
import os
import re
import secrets as _secrets
from pathlib import Path

import pytest

SERVER_SRC = Path(__file__).resolve().parent.parent / "server.py"


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _load_gate():
    src = SERVER_SRC.read_text(encoding="utf-8")
    m = re.search(
        r"\n_PLACEHOLDER_TOKENS = \{.*?\n\}\n"
        r"\n\ndef _check_index_token\(.*?(?=\n\n?@|\n\n?def |\n\n?async def )",
        src, re.S)
    assert m, "server.py 结构变化，请更新测试截取"
    ns = {"os": os, "secrets": _secrets, "HTTPException": HTTPException}
    exec(m.group(0), ns)
    return ns["_check_index_token"]


@pytest.fixture()
def gate():
    return _load_gate()


def test_unset_token_disables_writes(gate, monkeypatch):
    monkeypatch.delenv("TECHDB_QA_INDEX_TOKEN", raising=False)
    with pytest.raises(HTTPException) as ei:
        gate("anything")
    assert ei.value.status_code == 503
    assert "openssl rand -hex 32" in ei.value.detail


def test_placeholder_token_disables_writes(gate, monkeypatch):
    monkeypatch.setenv(
        "TECHDB_QA_INDEX_TOKEN", "replace_with_a_random_internal_index_token")
    with pytest.raises(HTTPException) as ei:
        gate("replace_with_a_random_internal_index_token")
    assert ei.value.status_code == 503
    assert "占位符" in ei.value.detail


def test_placeholder_with_surrounding_spaces_still_rejected(
        gate, monkeypatch):
    monkeypatch.setenv(
        "TECHDB_QA_INDEX_TOKEN",
        "  replace_with_a_random_internal_index_token  ")
    with pytest.raises(HTTPException) as ei:
        gate("replace_with_a_random_internal_index_token")
    assert ei.value.status_code == 503


def test_valid_token_mismatch_rejected_401(gate, monkeypatch):
    monkeypatch.setenv("TECHDB_QA_INDEX_TOKEN", "real-random-token")
    with pytest.raises(HTTPException) as ei:
        gate("wrong-token")
    assert ei.value.status_code == 401
    assert "invalid index token" in ei.value.detail


def test_valid_token_match_passes(gate, monkeypatch):
    tok = _secrets.token_hex(32)
    monkeypatch.setenv("TECHDB_QA_INDEX_TOKEN", tok)
    gate(tok)  # 不抛异常即放行
    gate(f"  {tok} ".strip())  # 环境变量侧已 strip，请求侧原值比对


def test_empty_request_token_rejected_401(gate, monkeypatch):
    monkeypatch.setenv("TECHDB_QA_INDEX_TOKEN", "real-random-token")
    with pytest.raises(HTTPException) as ei:
        gate(None)
    assert ei.value.status_code == 401

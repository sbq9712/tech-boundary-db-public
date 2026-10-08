"""Execute production resolver helpers without loading embedding models."""
import ast
import json
import threading
from pathlib import Path
from types import SimpleNamespace


def namespace():
    source = Path(__file__).resolve().parents[1] / "server.py"
    names = {"_record_key_sha_of", "_meta_record_key_sha", "_resolve_citation_results"}
    nodes = [n for n in ast.parse(source.read_text()).body
             if isinstance(n, ast.FunctionDef) and n.name in names]
    ns = {"json": json, "_incremental_index": SimpleNamespace(meta=[], _state_lock=threading.RLock()),
          "_record_ops_store": SimpleNamespace(tombstones=set(), is_base_masked=lambda key: False),
          "load_records": lambda: [{"t": "同名", "d": "2026-10-08", "u": ""}],
          "_result_allowed": lambda meta, base: meta.get("allowed", True)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
    return ns


def test_deleted_upload_never_falls_back_to_same_title_base():
    ns = namespace()
    assert ns["_resolve_citation_results"]([{"document_id": "deleted", "title": "同名",
                                           "date": "2026-10-08"}]) == []


def test_refresh_returns_current_chunk_not_cached_historical_text():
    ns = namespace()
    meta = {"document_id": "alive", "chunk_id": "new", "text": "current"}
    ns["_incremental_index"].meta = [meta]
    result = ns["_resolve_citation_results"]([{"document_id": "alive", "chunk_id": "old",
                                             "body_snippet": "deleted secret"}])
    assert result[0]["meta"] == meta
    meta["allowed"] = False
    assert ns["_resolve_citation_results"]([{"document_id": "alive"}]) == []


def test_base_refresh_uses_stable_identity_not_old_position():
    ns = namespace()
    key = ns["_record_key_sha_of"]("同名", "2026-10-08", "")
    selector = {"record_id": 9999, "record_key_sha": key}
    assert ns["_resolve_citation_results"]([selector])[0]["meta"]["idx"] == 0
    ns["_record_ops_store"].tombstones.add(key)
    assert ns["_resolve_citation_results"]([selector]) == []

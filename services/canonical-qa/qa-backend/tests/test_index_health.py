"""Codex 评审修复的回归测试（canonical-qa 增量索引真实健康信号）。

P1-4：documents_metadata 的 vector_rows_ok/bm25_rows_ok 逐 chunk 校验
对齐数组（embeddings 非零行 / corpus_tokens 非空词袋），索引结构损坏
（数组错位/缺行/BM25 未建）时不再只看 chunks>0 误报健康。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from incremental_index import IncrementalIndex
from rank_bm25 import BM25Okapi


def _mk_index(tmp_path: Path) -> IncrementalIndex:
    idx = IncrementalIndex(tmp_path / "inc.pkl", embedding_func=None)
    idx.loaded = True
    return idx


def _meta(did: str, chunk: str) -> dict:
    return {"document_id": did, "chunk_id": chunk, "b": "固态电池 能量密度",
            "chunk_metadata": {"primary_section": "industry"}}


def test_documents_metadata_reports_aligned_rows_healthy(tmp_path):
    idx = _mk_index(tmp_path)
    idx.meta = [_meta("d1", "c1"), _meta("d1", "c2"), _meta("d2", "c1")]
    idx.embeddings = np.ones((3, 1024), dtype=np.float32)
    idx.corpus_tokens = [["固态", "电池"], ["电解质"], ["回收"]]
    idx.bm25 = BM25Okapi(idx.corpus_tokens)
    out = idx.documents_metadata()
    assert out["d1"]["chunks"] == 2 and out["d2"]["chunks"] == 1
    assert out["d1"]["vector_rows_ok"] == 2
    assert out["d1"]["bm25_rows_ok"] == 2
    assert out["d2"]["vector_rows_ok"] == 1


def test_documents_metadata_detects_misaligned_arrays(tmp_path):
    """数组缺行（损坏加载/写入竞态）：chunks 在册但向量行不齐 → 不误报。"""
    idx = _mk_index(tmp_path)
    idx.meta = [_meta("d1", "c1"), _meta("d1", "c2")]
    idx.embeddings = np.ones((1, 1024), dtype=np.float32)   # 缺一行
    idx.corpus_tokens = [["固态"]]                          # 缺一行
    idx.bm25 = BM25Okapi(idx.corpus_tokens)
    out = idx.documents_metadata()
    assert out["d1"]["chunks"] == 2
    assert out["d1"]["vector_rows_ok"] == 0                 # 对齐失败 → 全不通过
    assert out["d1"]["bm25_rows_ok"] == 0


def test_documents_metadata_detects_zero_embedding_row(tmp_path):
    """零向量行（坏嵌入写入）：该 chunk 不可参与向量召回。"""
    idx = _mk_index(tmp_path)
    idx.meta = [_meta("d1", "c1"), _meta("d1", "c2")]
    emb = np.ones((2, 1024), dtype=np.float32)
    emb[1] = 0.0
    idx.embeddings = emb
    idx.corpus_tokens = [["a"], ["b"]]
    idx.bm25 = BM25Okapi(idx.corpus_tokens)
    out = idx.documents_metadata()
    assert out["d1"]["vector_rows_ok"] == 1
    assert out["d1"]["bm25_rows_ok"] == 2


def test_server_maps_health_fields_and_fallback_keeps_sources():
    """server.py 契约：状态端点消费 vector_rows_ok/bm25_rows_ok；编排降级
    检索保留 sources（P1-1）。源码断言，避免导入重型运行时。"""
    src = Path(__file__).resolve().parent.parent / "server.py"
    src = src.read_text(encoding="utf-8")
    assert 'entry.get("vector_rows_ok", chunks) == chunks' in src
    assert "await hybrid_search(base, sources=sources)" in src
    # P1-5：metadata patch 后 scoped 图谱缓存显式失效
    assert '_SCOPED_FRAGMENT_CACHE.update({"sig": "", "scopes": {}})' in src.split(
        "patched = await _incremental_index.patch_document_metadata")[1].split(
        "return {")[0]
    # P2-2 运行时半边：显式 unattributed 不被 VALID_SOURCES 过滤吞掉回退全源
    assert "if x in VALID_SOURCES) or VALID_SOURCES" not in src

"""任务二 2.4 回归：图谱碎片缓存签名必须覆盖真实内容与归属字段。

历史缺陷：fragment_signature 读 meta["checksum"]，而增量索引 meta 的
真实字段是 checksum_sha256——签名退化为 len+chunk keys，同记录数 UPDATE
（正文/类型/归属变化）不失效 scoped 碎片缓存，图谱继续返回旧实体/旧类别。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from graph_fragment import fragment_signature  # noqa: E402


def _row(key="doc-1-0", checksum_sha256="c1", section="breadth") -> dict:
    return {"key": key, "checksum_sha256": checksum_sha256,
            "chunk_metadata": {"primary_section": section}}


def test_signature_changes_on_content_update_same_keys():
    """复现审查缺陷：同记录数、同 chunk key，仅内容（checksum_sha256）
    变化 → 签名必须变化（scoped 缓存据此失效重建）。"""
    before = fragment_signature([_row()])
    after = fragment_signature([_row(checksum_sha256="c2")])
    assert before != after


def test_signature_changes_on_attribution_patch_same_content():
    """归属回填（primary_section 变化）改变 scope 视图 → 签名变化。"""
    before = fragment_signature([_row(section="industry")])
    after = fragment_signature([_row(section="atsc")])
    assert before != after


def test_signature_stable_when_nothing_changes():
    a = fragment_signature([_row(), _row(key="doc-1-1", checksum_sha256="c2")])
    b = fragment_signature([_row(), _row(key="doc-1-1", checksum_sha256="c2")])
    assert a == b


def test_signature_changes_on_row_removal_or_key_change():
    base = fragment_signature([_row(), _row(key="doc-1-1")])
    assert fragment_signature([_row()]) != base
    assert fragment_signature([_row(key="other")]) != base


def test_signature_reads_legacy_checksum_field_too():
    """旧形状 meta（chunk 顶层 checksum）也参与指纹——兼容历史索引数据。"""
    legacy_row = {"key": "doc-1-0", "checksum": "legacy"}
    assert fragment_signature([legacy_row]) != fragment_signature(
        [{"key": "doc-1-0", "checksum": "legacy2"}])

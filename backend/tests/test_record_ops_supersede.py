"""一.1 隔离验收：record 更新/删除后旧基础版本绝不回到召回面。

被复现缺陷：旧 clear_superseded_by_chunks 在新版本 upsert 落地后把
record_key_sha 移出遮蔽集合 → 基础索引旧版本从「禁止召回」变「允许召回」。
本测试用注入桩（无 fastapi / 无向量）驱动 record_ops.RecordOpsStore 全语义。
"""
import asyncio
import importlib
import sys

import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.services.qa_verification import record_ops as ro  # noqa: E402


class FakeIncremental:
    """增量索引桩：meta 携带 chunk_metadata.record_key_sha，可删可查。"""

    def __init__(self):
        self.meta = []
        self.alive = {}  # ksha -> [chunk texts]

    def seed(self, doc_id, ksha, chunks, content_sha="csha-default"):
        self.content_sha = content_sha
        for j, text in enumerate(chunks):
            self.meta.append({"document_id": doc_id, "text": text,
                              "chunk_metadata": {"record_key_sha": ksha,
                                                 "content_sha": content_sha}})
            self.alive.setdefault(ksha, []).append(text)

    def count_chunks_with_content(self, ksha, csha):
        return sum(1 for m in self.meta
                   if (m.get("chunk_metadata") or {}).get("record_key_sha") == ksha
                   and (m.get("chunk_metadata") or {}).get("content_sha") == csha)

    async def remove_chunks_by_record_keys(self, keys, exclude_content_shas=None):
        keys = {k for k in keys if k}
        keep = {c for c in (exclude_content_shas or set()) if c}
        removed = 0
        keep_meta = []
        for m in self.meta:
            md = m.get("chunk_metadata") or {}
            ksha = md.get("record_key_sha") or ""
            csha = md.get("content_sha") or ""
            if ksha and ksha in keys and not (csha and csha in keep):
                removed += 1
                lst = self.alive.get(ksha) or []
                if m["text"] in lst:
                    lst.remove(m["text"])
                if not lst:
                    self.alive.pop(ksha, None)
                continue
            keep_meta.append(m)
        self.meta = keep_meta
        return removed


BASE = ["ksha-base-1", "ksha-base-2", "ksha-base-3"]


def make_store(tmp_path, inc):
    return ro.RecordOpsStore(
        tmp_path / "record_ops_state.json",
        base_key_shas_fn=lambda: list(BASE),
        remove_chunks_fn=inc.remove_chunks_by_record_keys,
        on_change=lambda: None,
        count_chunks_with_content_fn=inc.count_chunks_with_content)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.new_event_loop().run_until_complete(coro)


def test_update_landed_keeps_base_masked(tmp_path):
    """核心回归：update → 新版本落地 → 基础旧版本仍被遮蔽（不得允许召回）。"""
    inc = FakeIncremental(); inc.seed("d1", "ksha-base-1", ["old chunk"])
    st = make_store(tmp_path, inc)
    # UPDATE：删旧增量 + pending 遮蔽基础
    _run(st.apply_async([{"record_key_sha": "ksha-base-1", "op": "update"}]))[0]
    assert st.is_base_masked("ksha-base-1") and "ksha-base-1" in st.superseded_pending
    assert inc.alive.get("ksha-base-1") in (None, [])
    # 新版本 upsert 落地（带同 record_key_sha 的新 chunk）
    inc.seed("d1", "ksha-base-1", ["new chunk"])
    st.mark_superseded_landed(["ksha-base-1"])
    # 一.1 断言：落地后基础遮蔽保持——「永久失效」而非「解除」
    assert st.is_base_masked("ksha-base-1")
    assert "ksha-base-1" in st.superseded_landed
    assert "ksha-base-1" not in st.superseded_pending
    assert 0 in st.superseded_base_positions  # 基础位置 0 仍被遮蔽


def test_restart_persists_masks(tmp_path):
    """更新成功、进程重启后遮蔽仍生效（持久化往返）。"""
    inc = FakeIncremental(); inc.seed("d1", "ksha-base-1", ["old"])
    st = make_store(tmp_path, inc)
    _run(st.apply_async([{"record_key_sha": "ksha-base-1", "op": "update"}]))[0]
    inc.seed("d1", "ksha-base-1", ["new"])
    st.mark_superseded_landed(["ksha-base-1"])
    # 新进程：重载磁盘状态
    st2 = make_store(tmp_path, inc)
    st2.load()
    assert st2.is_base_masked("ksha-base-1")
    assert "ksha-base-1" in st2.superseded_landed


def test_delete_after_landed_blocks_everything(tmp_path):
    """落地后再 DELETE：墓碑屏蔽基础与增量全链路；旧版本不回归。"""
    inc = FakeIncremental(); inc.seed("d1", "ksha-base-1", ["old"])
    st = make_store(tmp_path, inc)
    _run(st.apply_async([{"record_key_sha": "ksha-base-1", "op": "update"}]))[0]
    inc.seed("d1", "ksha-base-1", ["new"])
    st.mark_superseded_landed(["ksha-base-1"])
    _run(st.apply_async([{"record_key_sha": "ksha-base-1", "op": "delete"}]))[0]
    assert st.is_deleted_key("ksha-base-1")
    assert not st.is_base_masked("ksha-base-1")  # 墓碑接管（更强语义）
    assert 0 in st.deleted_base_positions        # 基础位置被墓碑遮蔽
    assert inc.alive.get("ksha-base-1") in (None, [])  # 新版本 chunk 也已删
    # 重启后依然
    st2 = make_store(tmp_path, inc); st2.load()
    assert st2.is_deleted_key("ksha-base-1")
    assert 0 in st2.deleted_base_positions


def test_import_upsert_supersedes_base_identity(tmp_path):
    """一.3/一.4：导入链 upsert 直接取代基础同身份记录（landed 登记）。"""
    inc = FakeIncremental()
    st = make_store(tmp_path, inc)
    inc.seed("import-doc", "ksha-base-2", ["imported content"])
    st.mark_superseded_landed(["ksha-base-2"])
    assert st.is_base_masked("ksha-base-2")
    assert 1 in st.superseded_base_positions  # ksha-base-2 → BASE[1]
    # 未知身份不登记（状态集不膨胀）
    st.mark_superseded_landed(["ksha-unknown-xyz"])
    assert "ksha-unknown-xyz" not in st.superseded_landed


def test_unblock_is_only_restore_channel(tmp_path):
    """唯一恢复通道 = 显式 unblock。"""
    inc = FakeIncremental(); inc.seed("d1", "ksha-base-3", ["old"])
    st = make_store(tmp_path, inc)
    _run(st.apply_async([{"record_key_sha": "ksha-base-3", "op": "update"}]))
    inc.seed("d1", "ksha-base-3", ["new"])
    st.mark_superseded_landed(["ksha-base-3"])
    assert st.is_base_masked("ksha-base-3")
    _run(st.apply_async([{"record_key_sha": "ksha-base-3", "op": "unblock"}]))[0]
    assert not st.is_base_masked("ksha-base-3")
    assert not st.is_deleted_key("ksha-base-3")


def test_startup_repair_exposes_nothing(tmp_path):
    """启动修复：旧代码遗留的暴露状态（增量存活 ∧ 基础同身份 ∧ 无遮蔽登记）
    补登 landed。幂等。"""
    inc = FakeIncremental(); inc.seed("d1", "ksha-base-1", ["new v"])
    st = make_store(tmp_path, inc)
    n = st.repair_landed_from_incremental(
        (m["chunk_metadata"]["record_key_sha"] for m in inc.meta))
    assert n == 1 and st.is_base_masked("ksha-base-1")
    # 幂等
    assert st.repair_landed_from_incremental(
        (m["chunk_metadata"]["record_key_sha"] for m in inc.meta)) == 0


def test_old_state_file_loaded_as_pending(tmp_path):
    """旧格式兼容：superseded_key_shas → pending（回滚安全）。"""
    import json
    f = tmp_path / "record_ops_state.json"
    f.write_text(json.dumps({"tombstones": {}, "superseded_key_shas": ["ksha-base-1"]}),
                 "utf-8")
    st = make_store(tmp_path, FakeIncremental())
    st.load()
    assert "ksha-base-1" in st.superseded_pending
    assert st.is_base_masked("ksha-base-1")
    # 落地转 landed 后旧键 = 并集（旧代码读取仍遮蔽）
    st.mark_superseded_landed(["ksha-base-1"])
    data = json.loads(f.read_text("utf-8"))
    assert set(data["superseded_key_shas"]) == {"ksha-base-1"}
    assert data["superseded_landed"] == ["ksha-base-1"]
    assert data["superseded_pending"] == []


def test_persist_atomic_write(tmp_path):
    """状态写入原子化：tmp + os.replace，无半写文件。"""
    import json
    inc = FakeIncremental()
    st = make_store(tmp_path, inc)
    _run(st.apply_async([{"record_key_sha": "ksha-base-1", "op": "delete"}]))[0]
    f = tmp_path / "record_ops_state.json"
    assert f.exists() and not (tmp_path / "record_ops_state.tmp").exists()
    data = json.loads(f.read_text("utf-8"))
    assert "ksha-base-1" in data["tombstones"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ── 一.2 幂等更新协议（重试丢记录缺陷的根修） ──────────────────────────

def test_update_resend_keeps_landed_new_version(tmp_path):
    """复现缺陷回归：UPDATE A、B 两键；A 批次已落地、B 未落地；重试重发
    record-mutate 不得删除 A 已落地的新版本 chunk。"""
    inc = FakeIncremental(); inc.seed("dA", "ksha-base-1", ["old A"])
    inc.seed("dB", "ksha-base-2", ["old B"])
    st = make_store(tmp_path, inc)
    NEW_A, NEW_B = "csha-A-new", "csha-B-new"
    # 第 1 轮：record-mutate（update A/B）成功
    _run(st.apply_async([
        {"record_key_sha": "ksha-base-1", "op": "update", "keep_content_sha": NEW_A},
        {"record_key_sha": "ksha-base-2", "op": "update", "keep_content_sha": NEW_B}]))
    # A 批次落地（新版本 chunk 入索引）
    inc.seed("docA", "ksha-base-1", ["new A"], content_sha=NEW_A)
    st.mark_superseded_landed(["ksha-base-1"])
    # 第 2 轮重试：重发同样的 record-mutate（超时重发语义）
    applied, details = _run(st.apply_async([
        {"record_key_sha": "ksha-base-1", "op": "update", "keep_content_sha": NEW_A},
        {"record_key_sha": "ksha-base-2", "op": "update", "keep_content_sha": NEW_B}]))
    by_k = {d["record_key_sha"]: d for d in details}
    # A：新版本 chunk 幸存 → landed 回执（不是被删）
    assert by_k["ksha-base-1"]["final_state"] == "landed"
    assert by_k["ksha-base-1"]["surviving_new_chunks"] == 1
    assert inc.alive.get("ksha-base-1") == ["new A"]  # 已落地新版本未被删除！
    # B：无新版本 → pending 回执
    assert by_k["ksha-base-2"]["final_state"] == "pending"
    assert by_k["ksha-base-2"]["surviving_new_chunks"] == 0


def test_update_without_keep_shares_old_semantics(tmp_path):
    """不带 keep_content_sha 的旧式 update：仍删全部旧 chunk + pending
    （向后兼容），但配合落地登记语义基础遮蔽不解除。"""
    inc = FakeIncremental(); inc.seed("d1", "ksha-base-1", ["old"])
    st = make_store(tmp_path, inc)
    applied, details = _run(st.apply_async(
        [{"record_key_sha": "ksha-base-1", "op": "update"}]))
    assert details[0]["final_state"] == "pending"
    assert inc.alive.get("ksha-base-1") in (None, [])
    assert st.is_base_masked("ksha-base-1")


def test_delete_resend_idempotent(tmp_path):
    """delete 重发：墓碑幂等、chunk 已删不报错、回执终态 tombstoned。"""
    inc = FakeIncremental(); inc.seed("d1", "ksha-base-1", ["c"])
    st = make_store(tmp_path, inc)
    for _ in range(2):
        applied, details = _run(st.apply_async(
            [{"record_key_sha": "ksha-base-1", "op": "delete"}]))
        assert details[0]["final_state"] == "tombstoned"
    assert st.is_deleted_key("ksha-base-1")
    assert inc.alive.get("ksha-base-1") in (None, [])

"""一.2 隔离验收：sync_qa_index 重试不再丢记录（替身服务端，stdlib-only）。

被复现缺陷（修复前）：UPDATE A、B 两批；第一批成功、第二批失败；重试
重新执行 record-mutate 删除 A 已落地的新版本，再按 pushed_doc_ids 跳过
A 批次 → A 从索引消失，基线却推进两条并返回 0。

修复后契约：
- mutate 重发幂等（keep_content_sha：服务端只删内容不匹配的旧 chunk）；
- 每批成功原子落盘回执（键→内容指纹）；
- 基线只按服务端确认（landed/tombstoned/同指纹批次回执）推进。
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import sync_qa_index as sq  # noqa: E402


class StubServer:
    """canonical-qa 增量索引替身：record-mutate 幂等语义 + upsert 去重。"""

    def __init__(self):
        self.chunks = []      # {doc_id, ksha, csha}
        self.tombstones = set()
        self.mutate_calls = 0
        self.deleted_ever = []   # (ksha, csha) 每次物理删除记录——断言新版本未被误删
        self.fail_batch = None   # 第 N 次批 upsert 抛 HTTPError
        self.upsert_calls = 0
        self.mutate_boom = False  # 模拟超时：服务端已应用后连接断

    def digest_of(self, rec):
        return sq.record_digest(rec)

    def mutate(self, ops):
        self.mutate_calls += 1
        boom = self.mutate_boom
        self.mutate_boom = False
        results = []
        for kh, op in ops:
            keep = op.get("keep_content_sha") or ""
            if op["op"] in ("update", "delete"):
                for c in [c for c in self.chunks if c["ksha"] == kh]:
                    if not (keep and c["csha"] == keep):
                        self.chunks.remove(c)
                        self.deleted_ever.append((kh, c["csha"]))
            if op["op"] == "delete":
                self.tombstones.add(kh)
                results.append({"record_key_sha": kh, "final_state": "tombstoned"})
            elif op["op"] == "update":
                surviving = sum(1 for c in self.chunks
                                if c["ksha"] == kh and c["csha"] == keep)
                results.append({"record_key_sha": kh,
                                "final_state": "landed" if surviving else "pending",
                                "surviving_new_chunks": surviving})
            else:
                results.append({"record_key_sha": kh, "final_state": "cleared"})
        if boom:
            raise OSError("simulated timeout after server apply")
        return {"status": "ok", "updated": len(ops), "results": results}

    def upsert(self, payload):
        self.upsert_calls += 1
        if self.fail_batch is not None and self.upsert_calls > self.fail_batch:
            self.fail_batch = None   # 只失败一次——重试轮允许全部成功
            import urllib.error
            raise urllib.error.HTTPError("stub", 503, "boom", {}, None)
        doc_id = payload["document_id"]
        for chunk in payload["chunks"]:
            md = chunk["metadata"]
            ksha, csha = md["record_key_sha"], md["content_sha"]
            # (ksha, csha) 跨文档去重（与服务端一致）
            if any(c["ksha"] == ksha and c["csha"] == csha for c in self.chunks):
                continue
            self.chunks = [c for c in self.chunks if c["doc_id"] != doc_id]
            self.chunks.append({"doc_id": doc_id, "ksha": ksha, "csha": csha})
        return {"status": "ready", "skipped_duplicate_chunks": 0}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    sq.STATE_PATH = tmp_path / "state.json"
    sq.SYNC_DIR = tmp_path
    sq.BASE_LITE = tmp_path / "base-lite.json"
    sq.LOCK_PATH = tmp_path / "sync.lock"
    sq.BATCH_RECORDS = 1
    monkeypatch.setattr(sq, "load_published_records", lambda: (RECORDS_V1, "test"))
    monkeypatch.setattr(sq, "baseline_key_hashes", lambda: BASELINE)
    return tmp_path


def kh_of(rec):
    return sq.key_digest(sq.record_key(rec))


R_A0 = {"t": "记录A", "d": "2026-01-01", "u": "http://x/a", "b": "old A content", "as": "", "a": "s", "c": "cat"}
R_A1 = {"t": "记录A", "d": "2026-01-01", "u": "http://x/a", "b": "NEW A content v1", "as": "", "a": "s", "c": "cat"}
R_B0 = {"t": "记录B", "d": "2026-01-02", "u": "http://x/b", "b": "old B content", "as": "", "a": "s", "c": "cat"}
R_B1 = {"t": "记录B", "d": "2026-01-02", "u": "http://x/b", "b": "NEW B content v1", "as": "", "a": "s", "c": "cat"}
BASELINE = {kh_of(R_A0): sq.record_digest(R_A0), kh_of(R_B0): sq.record_digest(R_B0)}
RECORDS_V1 = [R_A1, R_B1]


def run_sync(server):
    sq.post_record_ops = lambda ops, url, token: server.mutate(ops)
    sq.post_upsert = lambda payload, url, token: server.upsert(payload)
    return sq.main(["--qa-url", "http://stub"])


def test_two_updates_two_batches_midpoint_failure_retry(env):
    """核心缺陷回归：两批中途失败 → 重试 → A 新版本不被删、基线如实推进。"""
    server = StubServer()
    server.fail_batch = 1  # 第 1 次批 upsert（即批次 0/A）成功，第 2 次（批次 1/B）失败
    rc1 = run_sync(server)
    assert rc1 == 1
    state = json.loads(sq.STATE_PATH.read_text("utf-8"))
    kh_a = kh_of(R_A1)
    # 断点已落盘：批次 0 回执含 A 的新指纹
    assert state["in_flight"]["batch_receipts"], "批次回执必须已原子落盘"
    receipt = next(iter(state["in_flight"]["batch_receipts"].values()))
    assert receipt["cshas"] == {kh_a: sq.record_digest(R_A1)}
    # A 新版本在服务端存活（1 条 chunk）
    assert [c for c in server.chunks if c["ksha"] == kh_a and c["csha"] == sq.record_digest(R_A1)]

    # 重试：mutate 重发（幂等），A 跳过重推，B 补推
    rc2 = run_sync(server)
    assert rc2 == 0
    # A 的新版本 chunk 全程未被物理删除（缺陷：重试把它删了）
    kh_b = kh_of(R_B1)
    assert (kh_a, sq.record_digest(R_A1)) not in server.deleted_ever, \
        "重试不得删除已成功的新版本"
    # 终态：A、B 新版本各恰好一条；旧版本已清理
    assert sorted((c["ksha"], c["csha"]) for c in server.chunks) == sorted([
        (kh_a, sq.record_digest(R_A1)), (kh_b, sq.record_digest(R_B1))])
    # 基线推进两条且对应索引实际内容
    state2 = json.loads(sq.STATE_PATH.read_text("utf-8"))
    assert state2["key_hashes"] == {kh_a: sq.record_digest(R_A1),
                                    kh_b: sq.record_digest(R_B1)}
    assert not state2.get("pending_record_ops") and not state2.get("in_flight")


def test_timeout_after_server_apply(env):
    """超时后服务端已成功：客户端按 pending 保守处理、批次照推；下一轮
    mutate 重发拿到 landed 回执推进基线——内容不丢不重。"""
    server = StubServer()
    server.mutate_boom = True   # mutate 已应用后抛 OSError（模拟超时）
    rc1 = run_sync(server)
    # 保守：客户端无法确认服务端终态 → update 键基线不推进（返回 3）
    assert rc1 == 3
    state = json.loads(sq.STATE_PATH.read_text("utf-8"))
    assert set(state.get("pending_record_ops") or {}) == {kh_of(R_A1), kh_of(R_B1)}
    # 重跑：mutate 重发（幂等，服务端已应用 → 直接 landed）→ 基线推进
    rc2 = run_sync(server)
    assert rc2 == 0 and server.mutate_calls == 2
    state2 = json.loads(sq.STATE_PATH.read_text("utf-8"))
    assert state2["key_hashes"][kh_of(R_A1)] == sq.record_digest(R_A1)
    assert sum(1 for c in server.chunks if c["ksha"] == kh_of(R_A1)) == 1  # 不重不丢


def test_mutate_total_failure_keeps_pending(env):
    """mutate 整体失败（旧镜像 404）：批次照推（去重防重复），update 键
    基线不推进、留在 pending_record_ops，返回 3。"""
    server = StubServer()
    orig = sq.post_record_ops
    def _404(ops, url, token):
        import urllib.error
        raise urllib.error.HTTPError("stub", 404, "no endpoint", {}, None)
    sq.post_record_ops = _404
    sq.post_upsert = lambda payload, url, token: server.upsert(payload)
    rc = sq.main(["--qa-url", "http://stub"])
    assert rc == 3
    state = json.loads(sq.STATE_PATH.read_text("utf-8"))
    assert set(state.get("pending_record_ops") or {}) == {kh_of(R_A1), kh_of(R_B1)}
    # 基线未推进（保持旧 digest）
    assert state["key_hashes"] == BASELINE
    # 下一轮（服务端升级可用）：欠账补上
    rc2 = run_sync(server)
    assert rc2 == 0
    state2 = json.loads(sq.STATE_PATH.read_text("utf-8"))
    assert state2["key_hashes"][kh_of(R_A1)] == sq.record_digest(R_A1)
    # 去重：A 内容没有重复 chunk
    assert sum(1 for c in server.chunks if c["ksha"] == kh_of(R_A1)) == 1


def test_delete_retry_and_publish_view_change(env, monkeypatch):
    """DELETE 生效 + 发布视图在重试间变化：基线与索引一致，无幽灵记录。"""
    server = StubServer()
    monkeypatch.setattr(sq, "load_published_records", lambda: (RECORDS_V1[:1], "test"))
    rc = run_sync(server)   # B 从发布视图消失 → delete
    assert rc == 0
    kh_b = kh_of(R_B0)
    assert kh_b in server.tombstones
    assert kh_b not in json.loads(sq.STATE_PATH.read_text("utf-8"))["key_hashes"]
    # 发布视图又加回 A 的新版本 v2 → update 路径
    R_A2 = dict(R_A1, b="NEW A content v2")
    monkeypatch.setattr(sq, "load_published_records", lambda: ([R_A2], "test"))
    monkeypatch.setattr(sq, "baseline_key_hashes",
                        lambda: json.loads(sq.STATE_PATH.read_text("utf-8"))["key_hashes"])
    rc2 = run_sync(server)
    assert rc2 == 0
    assert sorted((c["ksha"], c["csha"]) for c in server.chunks) == [
        (kh_of(R_A1), sq.record_digest(R_A2))]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

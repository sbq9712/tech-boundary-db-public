"""T3/G1 + T4：canonical 增量索引损坏检测、epoch 重放、空 chunks 语义。

- incremental_index：文件损坏 → corrupt=True + reset epoch 持久递增 +
  health 增量就绪如实为 False；文件不存在 → healthy；恢复正常写入 →
  corrupt 清除。
- breadth_index_queue.check_incremental_reset_and_replay：新 epoch →
  done+upsert 全部重置 pending（delete 不动）；同 epoch 重复轮询不重放
  （qa_replay_state 持久确认）。
- _execute：upsert 空 chunks → 任务失败（no silent success）。
"""
import json
import os
import pickle
from pathlib import Path

import pytest
from sqlalchemy import text

os.environ.setdefault("TECHDB_BREADTH_INDEX_WORKER_ENABLED", "false")
os.environ.setdefault("TECHDB_UPLOAD_RECOVERY_ENABLED", "false")

from app.db.session import SessionLocal  # noqa: E402
from app.models.index_task import IndexTask  # noqa: E402
from app.services import breadth_index_queue as bq  # noqa: E402

QA_BACKEND = Path(__file__).resolve().parents[1].parent / \
    "services" / "canonical-qa" / "qa-backend"


# ── incremental_index：损坏检测 + epoch ────────────────────────────────

def _make_index(tmp_path, embedding=None):
    import sys
    sys.path.insert(0, str(QA_BACKEND))
    import incremental_index as inc
    idx = inc.IncrementalIndex(tmp_path / "index.pkl",
                               embedding or (lambda chunks: None))
    return inc, idx


def test_corrupt_file_sets_flag_and_epoch(tmp_path):
    inc, idx = _make_index(tmp_path)
    idx.path.write_bytes(b"not-a-pickle")
    idx.load()
    assert idx.loaded and idx.corrupt
    assert idx.reset_epoch >= 1
    assert json.loads((tmp_path / "reset-epoch.json").read_text())["epoch"] \
        == idx.reset_epoch


def test_missing_file_is_healthy(tmp_path):
    inc, idx = _make_index(tmp_path)
    idx.load()
    assert idx.loaded and not idx.corrupt
    assert idx.record_count == 0


def test_second_corruption_bumps_epoch(tmp_path):
    inc, idx = _make_index(tmp_path)
    idx.path.write_bytes(b"junk")
    idx.load()
    e1 = idx.reset_epoch
    idx2 = inc.IncrementalIndex(tmp_path / "index.pkl", lambda c: None)
    idx2.path.write_bytes(b"junk2")
    idx2.load()
    assert idx2.reset_epoch == e1 + 1


def test_valid_load_keeps_epoch_stable(tmp_path):
    import numpy as np
    inc, idx = _make_index(tmp_path)
    # 合法空索引文件（无 embedding 维度数据）
    payload = {"version": 1, "dim": 1024, "embeddings":
               np.zeros((0, 1024), dtype=np.float32), "meta": [],
               "corpus_tokens": []}
    idx.path.write_bytes(pickle.dumps(payload))
    idx.load()
    assert idx.loaded and not idx.corrupt and idx.record_count == 0


# ── check_incremental_reset_and_replay ────────────────────────────────

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, headers=None):
        return _FakeResp(self._payload)


@pytest.fixture()
def _db_rows():
    db = SessionLocal()
    ids = []
    up1 = IndexTask(op="upsert", target_key="t-replay-1", payload={},
                    status="done", rev=1)
    up2 = IndexTask(op="upsert", target_key="t-replay-2", payload={},
                    status="done", rev=1)
    dele = IndexTask(op="delete", target_key="t-replay-3", payload={},
                     status="done", rev=1)
    pend = IndexTask(op="upsert", target_key="t-replay-4", payload={},
                     status="pending", rev=1)
    db.add_all([up1, up2, dele, pend])
    db.commit()
    for t in (up1, up2, dele, pend):
        ids.append(str(t.id))
    db.execute(text(
        "INSERT INTO qa_replay_state (id, last_confirmed_epoch) "
        "VALUES (1, 0) ON CONFLICT (id) DO UPDATE SET last_confirmed_epoch=0"))
    db.commit()
    db.close()
    yield ids
    db = SessionLocal()
    try:
        for i in ids:
            db.execute(text("DELETE FROM breadth_index_tasks WHERE id=:i"),
                       {"i": i})
        db.execute(text("DELETE FROM qa_replay_state WHERE id=1"))
        db.commit()
    finally:
        db.close()


def test_new_epoch_replays_done_upserts_only(_db_rows, monkeypatch):
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://canonical-stub")

    def _client(timeout=None):
        return _FakeClient({"incremental_reset_epoch": 3})
    monkeypatch.setattr(bq.httpx, "Client", _client)
    n = bq.check_incremental_reset_and_replay()
    assert n == 2  # 两个 done upsert 被重置；delete/pending 不动
    db = SessionLocal()
    try:
        states = {t.target_key: t.status for t in
                  db.query(IndexTask).filter(
                      IndexTask.target_key.like("t-replay-%")).all()}
        assert states["t-replay-1"] == "pending"
        assert states["t-replay-2"] == "pending"
        assert states["t-replay-3"] == "done"   # delete 不重放
        assert "replay: canonical incremental index reset" in \
            db.get(IndexTask, db.query(IndexTask.id).filter_by(
                target_key="t-replay-1").scalar()).last_error
    finally:
        db.close()
    # 同 epoch 再轮询：不重复重放
    n2 = bq.check_incremental_reset_and_replay()
    assert n2 == 0


def test_epoch_downgrade_aligned_not_replayed(_db_rows, monkeypatch):
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://canonical-stub")

    def _client(timeout=None):
        return _FakeClient({"incremental_reset_epoch": 5})
    monkeypatch.setattr(bq.httpx, "Client", _client)
    assert bq.check_incremental_reset_and_replay() == 2

    def _client_low(timeout=None):
        return _FakeClient({"incremental_reset_epoch": 2})  # 卷重建回退
    monkeypatch.setattr(bq.httpx, "Client", _client_low)
    assert bq.check_incremental_reset_and_replay() == 0  # 对齐且不重放


def test_canonical_unreachable_is_silent(_db_rows, monkeypatch):
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://canonical-stub")

    def _boom(timeout=None):
        raise OSError("down")
    monkeypatch.setattr(bq.httpx, "Client", _boom)
    assert bq.check_incremental_reset_and_replay() == 0


def test_no_service_url_configured_skips(monkeypatch):
    monkeypatch.delenv("TECHDB_QA_SERVICE_URL", raising=False)
    assert bq.check_incremental_reset_and_replay() == 0


# ── T4：空 chunks 不再静默成功 ─────────────────────────────────────────

class _EmptyRecord:
    id = "00000000-0000-0000-0000-0000000000ee"
    upload_id = None
    content_hash = None
    source_ref = None


def test_empty_chunks_upsert_fails_with_reason(monkeypatch):
    """T4：记录存在但 title/ai_summary/body 全空 → _execute 抛错（任务转
    retry/failed），不再静默完成。记录不存在的"视为完成"语义保持独立。"""
    task = IndexTask(op="upsert", target_key=_EmptyRecord.id,
                     payload={"document_id": _EmptyRecord.id},
                     status="processing", rev=1)

    class _EmptyRec:
        id = _EmptyRecord.id
        upload_id = None
        content_hash = None
        source_ref = None
        title = ""
        ai_summary = ""
        body = ""
        document_date = ""
        source_name = ""
        url = ""
        category = ""
        intelligence_type = "news"
        tag = ""
        topic = ""
        ai_picked = False
        created_at = None

    class _Db:
        def get(self, model, pk):
            return _EmptyRec()

    payload = bq._upsert_payload(_EmptyRec())
    assert payload["chunks"] == []
    with pytest.raises(RuntimeError, match="empty payload"):
        bq._execute(_Db(), task)

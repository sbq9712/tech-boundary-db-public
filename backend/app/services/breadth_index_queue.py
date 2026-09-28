"""广度情报问答索引持久队列：入队 + 后台 worker（四/六节链路收口）。

链路：GitHub 增量包/逐行表格导入 → breadth_manual_records 落表 →
本队列入队 upsert → canonical-qa /api/index/upsert（bge-m3 向量 + BM25）
→ 门户问答经 /api/search 增量索引可检索；删除资料/包 → 入队 delete →
/api/index/delete → 索引不再召回。

保证：
- 持久化：任务先于导入事务提交落表，进程重启后 worker 续跑；
- 重试：指数退避（30s 起、封顶 1h），超过 MAX_ATTEMPTS 标记 failed，
  管理端重试入口可重新入队；
- 并发安全/不重复召回：target_key 唯一约束（同一目标只有一个任务行，
  重复入队覆盖为最新 op/payload）；canonical-qa upsert/delete 幂等，
  worker 顺序消费，重复执行无副作用；
- 崩溃恢复：启动时把遗留 processing 任务重置回 pending。
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.index_task import IndexTask

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 8
BACKOFF_BASE_SECONDS = 30.0
BACKOFF_CAP_SECONDS = 3600.0
POLL_SECONDS = 5.0
CLAIM_BATCH = 25
# 单记录最多入索引的分块数（正文上限 20000 字符，1200 字/块 ≈ 17 块封顶 12）
MAX_CHUNKS = 12
CHUNK_CHARS = 1200


# ── 入队 ────────────────────────────────────────────────────────────────


def enqueue_record_upserts(db: Session, records: list[BreadthManualRecord]) -> int:
    """为一批广度记录入队/覆盖 upsert 任务（与导入同一事务提交）。

    payload 只存 document_id：执行时由 worker 按 target_key 回读记录重建
    索引载荷——68k 级初始导入不会把任务表撑成记录体的又一份拷贝。"""
    n = 0
    for rec in records:
        _enqueue(db, op="upsert", target_key=str(rec.id),
                 payload={"document_id": str(rec.id)}, upload_id=rec.upload_id)
        n += 1
    return n


def enqueue_record_delete(db: Session, record_id: uuid.UUID | str, upload_id: uuid.UUID | None = None) -> None:
    _enqueue(db, op="delete", target_key=str(record_id), payload={"document_id": str(record_id)}, upload_id=upload_id)


def _enqueue(db: Session, *, op: str, target_key: str, payload: dict, upload_id) -> None:
    existing = db.scalar(select(IndexTask).where(IndexTask.target_key == target_key))
    if existing is None:
        db.add(
            IndexTask(
                op=op, target_key=target_key, payload=payload,
                upload_id=upload_id, status="pending",
            )
        )
        return
    # 同目标已有任务（可能还在退避等待）：覆盖为最新操作并立即回到待处理
    existing.op = op
    existing.payload = payload
    existing.upload_id = upload_id or existing.upload_id
    existing.status = "pending"
    existing.not_before = None
    existing.last_error = None
    if existing.attempts >= MAX_ATTEMPTS:
        existing.attempts = 0  # 显式重新入队视为人工/新数据触发，重置计数


def _upsert_payload(rec: BreadthManualRecord) -> dict:
    text = "\n".join(
        part for part in (rec.title or "", rec.ai_summary or "", rec.body or "") if part
    ).strip()
    chunks: list[dict] = []
    if text:
        for i in range(0, len(text), CHUNK_CHARS):
            if len(chunks) >= MAX_CHUNKS:
                break
            piece = text[i : i + CHUNK_CHARS]
            chunks.append(
                {
                    "chunk_id": f"{rec.id}-{len(chunks)}",
                    "text": piece,
                    # chunk 级溯源键：canonical-qa 增量索引据此生成引用卡
                    # （标题/日期/来源/链接）并参与跨索引去重
                    "title": rec.title or "",
                    "record_date": rec.document_date or "",
                    "source_name": rec.source_name or "",
                    "url": rec.url or "",
                    "summary": (rec.ai_summary or "")[:300],
                    "metadata": {
                        "document_date": rec.document_date or "",
                        "url": rec.url or "",
                        "source_name": rec.source_name or "",
                        "intelligence_type": rec.intelligence_type or "news",
                        "tag": rec.tag or "",
                        "topic": rec.topic or "",
                        "ai_picked": bool(rec.ai_picked),
                        "source": "breadth-import",
                    },
                }
            )
    return {
        "document_id": str(rec.id),
        # canonical-qa 的 filename 声明为 str（不接受 null）——source_ref
        # 缺 file 时必须落空串，否则整条 422 进不了增量索引
        "filename": (rec.source_ref or {}).get("file") if isinstance(rec.source_ref, dict) else "",
        "title": rec.title or "",
        "primary_category": rec.category or "未分类",
        "secondary_categories": [],
        "source_type": "breadth-import",
        "checksum_sha256": rec.content_hash,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "chunks": chunks,
    }


# ── 执行 ────────────────────────────────────────────────────────────────


def _post_index_upsert(payload: dict) -> dict:
    import os

    base_url = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TECHDB_QA_SERVICE_URL 未配置，无法写入增量索引")
    timeout = float(os.getenv("TECHDB_QA_INDEX_TIMEOUT_SECONDS", "300"))
    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    headers = {"X-TechDB-Index-Token": token} if token else {}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/api/index/upsert", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
    if result.get("status") != "ready":
        raise RuntimeError("canonical-qa 未确认增量索引已写入")
    return result


def _post_index_delete(document_id: str) -> None:
    import os

    # 未配置检索服务时该环境本就从未入索引——删除视为幂等成功
    base_url = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    if not base_url:
        return
    from app.services.upload_ingestion import request_incremental_index_delete

    # 复用上传链路的幂等删除
    request_incremental_index_delete(document_id)


def _execute(db: Session, task: IndexTask) -> None:
    document_id = str((task.payload or {}).get("document_id") or task.target_key)
    if task.op == "delete":
        _post_index_delete(document_id)
        return
    rec = db.get(BreadthManualRecord, _as_uuid(document_id))
    if rec is None:
        # 目标记录已不存在（包重导/记录被删）：无需写入，视为完成
        return
    payload = _upsert_payload(rec)
    if not payload["chunks"]:
        return
    _post_index_upsert(payload)


def _as_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(str(value))


def process_batch(db: Session | None = None) -> int:
    """认领并执行一批到期任务。返回处理条数（供测试/单步驱动）。"""
    own = db is None
    db = db or SessionLocal()
    now = datetime.now(timezone.utc)
    try:
        ids = db.scalars(
            select(IndexTask.id)
            .where(
                IndexTask.status == "pending",
                (IndexTask.not_before.is_(None)) | (IndexTask.not_before <= now),
                IndexTask.attempts < MAX_ATTEMPTS,
            )
            .order_by(IndexTask.created_at)
            .limit(CLAIM_BATCH)
        ).all()
        if not ids:
            return 0
        claimed = db.execute(
            update(IndexTask)
            .where(IndexTask.id.in_(ids), IndexTask.status == "pending")
            .values(status="processing", attempts=IndexTask.attempts + 1)
        )
        db.commit()
        if claimed.rowcount == 0:
            return 0
        done = 0
        for tid in ids:
            task = db.get(IndexTask, tid)
            if task is None or task.status != "processing":
                continue
            try:
                _execute(db, task)
            except Exception as exc:  # noqa: BLE001 — 单任务失败不拖垮整批
                _mark_retry_or_failed(db, task, str(exc)[:2000])
            else:
                task.status = "done"
                task.last_error = None
                task.not_before = None
                db.commit()
                _finalize_upload_status(db, task.upload_id)
                done += 1
        return done
    finally:
        if own:
            db.close()


def _mark_retry_or_failed(db: Session, task: IndexTask, message: str) -> None:
    if task.attempts >= MAX_ATTEMPTS:
        task.status = "failed"
        task.last_error = message
        db.commit()
        logger.error("index task %s failed permanently: %s", task.target_key, message)
        return
    delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** max(0, task.attempts - 1)))
    task.status = "pending"
    task.last_error = message
    task.not_before = datetime.now(timezone.utc) + timedelta(seconds=delay)
    db.commit()
    logger.warning("index task %s attempt %s failed, retry in %.0fs: %s",
                   task.target_key, task.attempts, delay, message)


def _finalize_upload_status(db: Session, upload_id: uuid.UUID | None) -> None:
    """上传聚合状态：其全部任务终结（done/failed）后回落 ready/failed。"""
    if upload_id is None:
        return
    from app.models.uploaded_file import UploadedFile

    remaining = db.scalar(
        select(IndexTask.id).where(
            IndexTask.upload_id == upload_id,
            IndexTask.status.in_(("pending", "processing")),
        )
    )
    if remaining is not None:
        return
    failed = db.scalar(
        select(IndexTask.id).where(
            IndexTask.upload_id == upload_id, IndexTask.status == "failed"
        )
    )
    db.execute(
        update(UploadedFile)
        .where(UploadedFile.id == upload_id)
        .values(embedding_status="failed" if failed is not None else "ready",
                embedded_at=datetime.now(timezone.utc))
    )
    db.commit()


def recover_stale_processing() -> int:
    """启动恢复：上一进程崩溃时遗留的 processing 任务重回 pending。

    upsert/delete 幂等，重复执行安全。"""
    db = SessionLocal()
    try:
        result = db.execute(
            update(IndexTask)
            .where(IndexTask.status == "processing")
            .values(status="pending")
        )
        db.commit()
        if result.rowcount:
            logger.warning("recovered %s stale processing index tasks", result.rowcount)
        return int(result.rowcount or 0)
    finally:
        db.close()


def run_worker(poll_seconds: float = POLL_SECONDS) -> None:
    """守护线程主体：与 upload_ingestion.recover_pending_uploads 同一模式。"""
    recover_stale_processing()
    while True:
        try:
            processed = process_batch()
        except Exception:  # noqa: BLE001
            logger.exception("breadth index worker iteration failed")
            processed = 0
        if not processed:
            time.sleep(poll_seconds)

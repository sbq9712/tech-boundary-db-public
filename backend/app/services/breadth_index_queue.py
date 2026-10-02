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


def enqueue_record_delete(db: Session, record_id: uuid.UUID | str,
                          upload_id: uuid.UUID | None = None,
                          record_key_sha: str | None = None,
                          *, row: BreadthManualRecord | None = None) -> None:
    """入队删除任务（二）：调用方必须在删除数据库行之前入队，并把统一身份
    record_key_sha 一并持久化进 payload——任务异步执行时行多半已删，
    仅凭 document_id（数据库 UUID）无法再对齐基础索引同身份旧版本，
    DELETE-before-first-ADD（行不存在但已烘焙进基础索引）也全靠它。
    传 row 时由本函数计算 ksha，调用方无需重复拼身份三元组。"""
    payload: dict = {"document_id": str(record_id)}
    ksha = record_key_sha
    if ksha is None and row is not None:
        ksha = canonical_record_key_sha(
            row.title, row.document_date or "", row.url or "")
    if ksha:
        payload["record_key_sha"] = str(ksha)
    _enqueue(db, op="delete", target_key=str(record_id), payload=payload,
             upload_id=upload_id)


def _enqueue(db: Session, *, op: str, target_key: str, payload: dict, upload_id) -> None:
    existing = db.scalar(select(IndexTask).where(IndexTask.target_key == target_key))
    if existing is None:
        db.add(
            IndexTask(
                op=op, target_key=target_key, payload=payload,
                upload_id=upload_id, status="pending", rev=1,
            )
        )
        return
    # 同目标已有任务（可能还在退避等待）：覆盖为最新操作并立即回到待处理。
    # 二.2：rev 自增 = 修订号——执行中的旧 worker 完成回写按 (rev, claim_token)
    # 条件更新，被重新入队后旧回写作废，旧任务不能把新任务标记 done。
    existing.op = op
    existing.payload = payload
    existing.upload_id = upload_id or existing.upload_id
    existing.status = "pending"
    existing.not_before = None
    existing.last_error = None
    existing.rev = (existing.rev or 0) + 1
    existing.claim_token = None      # 旧认领即刻作废
    existing.lease_expires_at = None
    if existing.attempts >= MAX_ATTEMPTS:
        existing.attempts = 0  # 显式重新入队视为人工/新数据触发，重置计数


def canonical_record_key_sha(title: str, document_date: str, url: str) -> str:
    """一.3 统一身份：与 canonical-qa server._record_key_sha_of /
    sync_qa_index.key_digest 同源同值——sha256(json([t,d,u]))。导入链的
    增量 chunk 与基础索引记录以同一身份对齐（跨路径去重/替换遮蔽/删除
    墓碑都按它生效），不再只靠数据库 UUID。"""
    import hashlib as _hashlib
    import json as _json
    return _hashlib.sha256(_json.dumps(
        [str(title or ""), str(document_date or ""), str(url or "")],
        ensure_ascii=False).encode("utf-8")).hexdigest()


def _rec_content_sha(rec: BreadthManualRecord) -> str:
    """导入链内容指纹：content_hash 即入库时计算的 v2 哈希；缺失时按
    正文派生（与记录修订判定一致的分母）。"""
    import hashlib as _hashlib
    return rec.content_hash or _hashlib.sha256(
        f"{rec.title}|{rec.document_date}|{rec.body or ''}".encode("utf-8")).hexdigest()


def _rec_origin_section(rec: BreadthManualRecord) -> str:
    """任务二 2.1：记录原始栏目（breadth/industry/atsc）。

    旧数据 origin_section 可能为 NULL（迁移回填前已入库）——按 FK 匹配
    100% 可回填的前提，这里做读取侧兜底：不可追溯落 breadth 语义并由
    回填脚本收敛（/api/index/status 会把无归属文档单独列出，不猜测）。
    """
    section = (getattr(rec, "origin_section", None) or "").strip().lower()
    return section if section in ("breadth", "industry", "atsc") else "breadth"


_SECTION_SOURCE_TYPE = {
    "breadth": "breadth-import",
    "industry": "industry-import",
    "atsc": "atsc-import",
}


def _upsert_payload(rec: BreadthManualRecord, rev: int = 0) -> dict:
    text = "\n".join(
        part for part in (rec.title or "", rec.ai_summary or "", rec.body or "") if part
    ).strip()
    origin_section = _rec_origin_section(rec)
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
                        # 任务二 2.1：来源归属贯通——不再统一 breadth-import，
                        # 按记录原始栏目落值（检索分域/引用归属/图谱 scope 用）
                        "source": _SECTION_SOURCE_TYPE.get(origin_section, "breadth-import"),
                        "primary_section": origin_section,
                        # 一.3/一.4：统一记录身份 + 内容指纹 + 队列修订号——
                        # 服务端据此做同身份去重、基础旧版本替换遮蔽、
                        # 迟到旧版本拒绝（source_rev 严格递减拒收）
                        "record_key_sha": canonical_record_key_sha(
                            rec.title, rec.document_date or "", rec.url or ""),
                        "content_sha": _rec_content_sha(rec),
                        "source_rev": int(rev),
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
        "source_type": _SECTION_SOURCE_TYPE.get(origin_section, "breadth-import"),
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
        # Codex P1（spec 评审）：全拒收（墓碑/迟到旧版本）必须如实失败——
        # 「收到写请求」≠「已可检索」。补录顺序契约：unblock → upsert。
        rejected = (int(result.get("rejected_tombstoned_chunks") or 0)
                    + int(result.get("rejected_stale_rev_chunks") or 0))
        detail = ""
        if rejected:
            detail = (f"（拒绝 {rejected} chunk：墓碑/旧版本拒收——"
                      f"如为删除后补录，请先经包通道 unblock 再重试）")
        raise RuntimeError(
            f"canonical-qa 未确认增量索引已写入：status={result.get('status')}{detail}")
    return result


def _post_index_delete(document_id: str) -> None:
    import os

    # 未配置检索服务时该环境本就从未入索引——删除视为幂等成功
    base_url = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    if not base_url:
        return
    from app.services.upload_ingestion import request_incremental_index_delete

    # 复用上传链路的幂等删除（按 document_id 删增量文档）
    request_incremental_index_delete(document_id)


_record_mutate_supported: bool | None = None


def _post_record_mutate_delete(record_key_sha: str) -> None:
    """一.4（2026-09-30）：源 DELETE 不能只删数据库 UUID 对应的增量文档——
    同身份的基础索引旧版本必须被墓碑屏蔽（否则旧版本继续可召回）。
    record-mutate delete 幂等：重复发送安全。
    二：404 不再静默当成功——首次 404 探测端点能力，确认是旧镜像后
    如实抛错（任务进失败待办可重试/可审计），而不是假装删除完成。"""
    import os

    global _record_mutate_supported
    base_url = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    if not base_url:
        return
    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    headers = {"X-TechDB-Index-Token": token, "Content-Type": "application/json"}
    timeout = float(os.getenv("TECHDB_QA_INDEX_TIMEOUT_SECONDS", "300"))
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            f"{base_url}/api/index/record-mutate", headers=headers,
            json={"ops": [{"record_key_sha": record_key_sha, "op": "delete",
                           "reason": "breadth-import-delete"}]})
        if resp.status_code == 404:
            if _record_mutate_supported is None:
                _record_mutate_supported = False
            if not _record_mutate_supported:
                raise RuntimeError(
                    "canonical-qa /api/index/record-mutate 不存在（镜像过旧）——"
                    "同身份基础索引旧版本未被墓碑屏蔽，任务转失败待办，"
                    "镜像升级后会随重试完成")
            return
        _record_mutate_supported = True
        resp.raise_for_status()


def _execute(db: Session, task: IndexTask) -> None:
    document_id = str((task.payload or {}).get("document_id") or task.target_key)
    if task.op == "delete":
        _post_index_delete(document_id)
        rec = None
        try:
            rec = db.get(BreadthManualRecord, _as_uuid(document_id))
        except Exception:  # noqa: BLE001 — UUID 解析失败按无记录处理
            rec = None
        ksha = None
        if rec is not None:
            ksha = canonical_record_key_sha(
                rec.title, rec.document_date or "", rec.url or "")
        elif task.payload and task.payload.get("record_key_sha"):
            ksha = str(task.payload["record_key_sha"])
        if ksha:
            _post_record_mutate_delete(ksha)  # 一.4：同身份基础旧版本一并屏蔽
        else:
            # 二：行与 payload 都拿不到统一身份 = 无法证明基础索引旧版本
            # 已被屏蔽。增量文档虽删，烘焙基础 B 仍可能继续可召回——
            # 如实失败进退避重试（记录行若被恢复/新包重导可补齐身份），
            # 不允许假装删除完成。
            raise RuntimeError(
                f"delete task {task.id} 缺少统一身份（记录行不存在且 payload "
                f"无 record_key_sha）——同身份基础索引旧版本屏蔽无法保证，"
                f"拒绝静默完成")
        return
    rec = db.get(BreadthManualRecord, _as_uuid(document_id))
    if rec is None:
        # 目标记录已不存在（包重导/记录被删）：无需写入，视为完成
        return
    payload = _upsert_payload(rec, rev=task.rev or 0)
    if not payload["chunks"]:
        # T4（2026-10-02）：空文本（title/summary/body 全空）的 upsert 不再
        # 静默成功——导入链 title 必填，空文本属异常数据；如实失败进
        # retry/failed（last_error 可审计），避免"协议层吞错假装完成"。
        raise RuntimeError(
            f"empty payload: record {document_id} has no indexable text "
            "(title/ai_summary/body all empty)")
    _post_index_upsert(payload)


def _as_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(str(value))


LEASE_SECONDS = float(__import__("os").environ.get("TECHDB_INDEX_LEASE_SECONDS", "900"))


def process_batch(db: Session | None = None) -> int:
    """认领并执行一批到期任务。返回处理条数（供测试/单步驱动）。

    二.2 认领协议：每任务认领时生成 claim_token + 租约（默认 15 分钟）；
    完成/失败回写必须条件命中 (id, status=processing, claim_token, rev)——
    执行期间被重新入队（rev/claim_token 变化）后旧 worker 的回写被拒绝，
    旧任务不能把新任务标记 done。"""
    import os as _os
    import uuid as _uuid

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
        # 逐任务认领：status 条件更新（pending→processing）+ claim token +
        # 租约 + rev 自增，一次 update 完成条件竞争安全的认领
        tokens: dict[str, str] = {}
        for tid in ids:
            token = str(_uuid.uuid4())
            res = db.execute(
                update(IndexTask)
                .where(IndexTask.id == tid, IndexTask.status == "pending")
                .values(status="processing", attempts=IndexTask.attempts + 1,
                        rev=IndexTask.rev + 1, claim_token=token,
                        lease_expires_at=now + timedelta(seconds=LEASE_SECONDS))
                .execution_options(synchronize_session=False))
            if res.rowcount:
                tokens[str(tid)] = token
        db.commit()
        if not tokens:
            return 0
        done = 0
        for tid, token in tokens.items():
            task = db.get(IndexTask, tid)
            if task is None or task.status != "processing" \
                    or task.claim_token != token:
                continue  # 租约已被重新入队/其他 worker 接管
            claimed_rev = task.rev
            try:
                _execute(db, task)
            except Exception as exc:  # noqa: BLE001 — 单任务失败不拖垮整批
                _mark_retry_or_failed(db, task, str(exc)[:2000], token, claimed_rev)
            else:
                # 条件完成：只完成自己认领的任务版本（token+rev 未变）
                res = db.execute(
                    update(IndexTask)
                    .where(IndexTask.id == task.id,
                           IndexTask.status == "processing",
                           IndexTask.claim_token == token,
                           IndexTask.rev == claimed_rev)
                    .values(status="done", last_error=None, not_before=None,
                            claim_token=None, lease_expires_at=None)
                    .execution_options(synchronize_session=False))
                db.commit()
                if res.rowcount:
                    _finalize_upload_status(db, task.upload_id)
                    done += 1
                else:
                    logger.info(
                        "index task %s completion rejected (re-enqueued during "
                        "execution, rev/claim mismatch)", tid)
        return done
    finally:
        if own:
            db.close()


def _mark_retry_or_failed(db: Session, task: IndexTask, message: str,
                          claim_token: str | None = None,
                          claimed_rev: int | None = None) -> None:
    """失败回写同样条件化（二.2）：只有仍持有认领（token/rev 未变）才能
    改状态——失败不算完成，也不能覆盖已重新入队的新版本。"""
    cond = [IndexTask.id == task.id, IndexTask.status == "processing"]
    if claim_token:
        cond.append(IndexTask.claim_token == claim_token)
    if claimed_rev is not None:
        cond.append(IndexTask.rev == claimed_rev)
    values: dict = {"last_error": message}
    if task.attempts >= MAX_ATTEMPTS:
        values["status"] = "failed"
        values["claim_token"] = None
        values["lease_expires_at"] = None
    else:
        delay = min(BACKOFF_CAP_SECONDS,
                    BACKOFF_BASE_SECONDS * (2 ** max(0, task.attempts - 1)))
        values["status"] = "pending"
        values["not_before"] = datetime.now(timezone.utc) + timedelta(seconds=delay)
    res = db.execute(update(IndexTask).where(*cond).values(**values)
                     .execution_options(synchronize_session=False))
    db.commit()
    if not res.rowcount:
        logger.info("index task %s failure write-back rejected (stale claim)",
                    task.target_key)
        return
    if values["status"] == "failed":
        logger.error("index task %s failed permanently: %s", task.target_key, message)
    else:
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
    """恢复只回收【过期租约】的 processing 任务（二.2）：租约未到期的
    可能是其他进程的活跃 worker，绝不重置。无租约的遗留行（升级前数据）
    一并回收。upsert/delete 幂等，重复执行安全。"""
    db = SessionLocal()
    try:
        result = db.execute(
            update(IndexTask)
            .where(IndexTask.status == "processing",
                   (IndexTask.lease_expires_at.is_(None))
                   | (IndexTask.lease_expires_at <= datetime.now(timezone.utc)))
            .values(status="pending", claim_token=None, lease_expires_at=None)
        )
        db.commit()
        if result.rowcount:
            logger.warning("recovered %s stale (expired-lease) index tasks",
                           result.rowcount)
        return int(result.rowcount or 0)
    finally:
        db.close()


def run_worker(poll_seconds: float = POLL_SECONDS) -> None:
    """守护线程主体：与 upload_ingestion.recover_pending_uploads 同一模式。

    T3/G1：每小时轮询 canonical-qa 增量索引 reset epoch，损坏清空后自动
    幂等重放全部 done upsert 任务（重放后 canonical 恢复写入即回到 healthy）。
    """
    recover_stale_processing()
    epoch_check_at = 0.0
    EPOCH_POLL_SECONDS = 3600.0
    while True:
        now = time.monotonic()
        if now - epoch_check_at >= EPOCH_POLL_SECONDS:
            epoch_check_at = now
            try:
                check_incremental_reset_and_replay()
            except Exception:  # noqa: BLE001 — 轮询异常不影响主循环
                logger.exception("incremental reset epoch check failed")
        try:
            processed = process_batch()
        except Exception:  # noqa: BLE001
            logger.exception("breadth index worker iteration failed")
            processed = 0
        if not processed:
            time.sleep(poll_seconds)


# ── T3/G1：canonical 增量索引损坏重放（2026-10-02）────────────────────


def check_incremental_reset_and_replay() -> int:
    """轮询 canonical-qa /api/health 的 reset epoch：发现新 epoch 即把全部
    done+upsert 任务重置 pending（幂等重放）。

    - 触发条件：incremental_reset_epoch > 本地已确认 epoch（qa_replay_state
      单行持久——api 重启不重复/不漏触发）；
    - 只重放 upsert：delete 的墓碑独立持久，不受增量清空影响；
    - canonical 不可达/字段缺失：静默跳过（下小时再查），不抛错拖垮 worker；
    - 返回重置条数（供测试与日志）。
    """
    import os

    base_url = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    if not base_url:
        return 0
    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    headers = {"X-TechDB-Index-Token": token} if token else {}
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{base_url}/api/health", headers=headers)
            resp.raise_for_status()
            health = resp.json()
        epoch = int(health.get("incremental_reset_epoch") or 0)
    except Exception:  # noqa: BLE001 — 诊断轮询失败不影响队列主循环
        logger.debug("incremental reset epoch poll failed", exc_info=True)
        return 0

    from app.models.qa_replay_state import QaReplayState

    db = SessionLocal()
    try:
        row = db.get(QaReplayState, 1)
        if row is None:
            row = QaReplayState(id=1, last_confirmed_epoch=0)
            db.add(row)
            db.flush()
        if epoch <= row.last_confirmed_epoch:
            row.last_confirmed_epoch = epoch  # 对齐（canonical 可能回退重建）
            db.commit()
            return 0
        res = db.execute(
            update(IndexTask)
            .where(IndexTask.status == "done", IndexTask.op == "upsert")
            .values(status="pending", attempts=0, not_before=None,
                    last_error="replay: canonical incremental index reset "
                               f"(epoch {epoch})", claim_token=None,
                    lease_expires_at=None)
            .execution_options(synchronize_session=False))
        replayed = int(res.rowcount or 0)
        row.last_confirmed_epoch = epoch
        db.commit()
        if replayed:
            logger.warning(
                "canonical incremental index reset (epoch=%s) — requeued %s "
                "done upsert tasks for idempotent replay", epoch, replayed)
        return replayed
    finally:
        db.close()

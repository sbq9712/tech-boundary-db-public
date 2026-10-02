"""任务一 1.1：上传真实可检索状态（状态契约）。

「已可检索」的唯一权威是 canonical-qa 增量索引实际内容
（GET /api/index/status?document_ids=...，token 保护）。本模块聚合三层：

1. DB（uploaded_files.embedding_status/chunk_count）；
2. 持久队列（breadth_index_tasks 按上传 GROUP BY）——GitHub 增量包/
   逐行表格链路的索引写入是异步任务，DB 字段只表达入队意图；
3. canonical-qa（按记录 document_id 逐文档确认 chunks/vector_ok/bm25_ok）。

列表端点用单条 GROUP BY 映射粗状态（不做 N 次 canonical 调用）；
详情端点 /uploads/{id}/index-status 做全量聚合，是上传页展示与轮询
（1.3）的唯一数据源。canonical 不可达时如实返回 unknown（searchable
= None），绝不假装可检索。
"""

from __future__ import annotations

import os
import uuid
from collections import defaultdict

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.breadth_import_session import BreadthImportSession
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.index_task import IndexTask
from app.models.uploaded_file import UploadedFile

# GitHub 分支列表态词汇（spec 1.1）：队列映射的粗状态
GITHUB_QUEUE_STATUSES = (
    "index_failed",
    "index_processing",
    "index_queued",
    "indexed",
    "import_failed",
    "no_new_records",
    "legacy_unknown",
)


def queue_aggregate(
    db: Session, upload_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    """单条 GROUP BY 拿到每上传的任务状态计数（列表页专用，无 N+1）。"""
    if not upload_ids:
        return {}
    rows = db.execute(
        select(IndexTask.upload_id, IndexTask.status, func.count())
        .where(IndexTask.upload_id.in_(upload_ids))
        .group_by(IndexTask.upload_id, IndexTask.status)
    ).all()
    agg: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)
    for upload_id, status, count in rows:
        if upload_id is None:
            continue
        agg[upload_id][str(status)] = int(count)
    return dict(agg)


def sessions_map(
    db: Session, upload_ids: list[uuid.UUID]
) -> dict[uuid.UUID, BreadthImportSession]:
    if not upload_ids:
        return {}
    rows = db.scalars(
        select(BreadthImportSession).where(BreadthImportSession.upload_id.in_(upload_ids))
    ).all()
    return {row.upload_id: row for row in rows}


def _record_count(db: Session, upload_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(BreadthManualRecord).where(
                BreadthManualRecord.upload_id == upload_id
            )
        )
        or 0
    )


def map_github_status(
    record: UploadedFile,
    tasks: dict[str, int],
    session: BreadthImportSession | None,
    live_records: int | None = None,
) -> tuple[str, dict]:
    """GitHub 增量包分支的真实状态映射。

    优先级（先看导入结果，再看索引任务）：
    - 会话存在：failed>0 且 imported==0 → import_failed（包解析/校验失败）；
      imported==0 且 skipped>0 → no_new_records（全部记录由上游管线持有
      或重复，本包无可索引新增——检索面走管线语料，不缺证据）；
    - 队列：failed>0 → index_failed；processing>0 → index_processing；
      pending>0 → index_queued；total>0 全 done → indexed；
    - 无会话无任务：queued 挂起 → legacy_unknown（导入中断/早期上传，
      重试 = 重新导入）。
    """
    total = sum(tasks.values())
    detail = {
        "tasks_total": total,
        "tasks_done": tasks.get("done", 0),
        "tasks_failed": tasks.get("failed", 0),
        "tasks_pending": tasks.get("pending", 0),
        "tasks_processing": tasks.get("processing", 0),
    }
    if session is not None:
        detail["session"] = {
            "package_date": session.package_date,
            "record_count": session.record_count,
            "imported": session.imported,
            "skipped_duplicate": session.skipped_duplicate,
            "skipped_upstream_conflict": session.skipped_upstream_conflict,
            "failed": session.failed,
            "package_deduplicated": bool(session.package_deduplicated),
            "replayed": bool(session.replayed),
        }
        if session.failed > 0 and session.imported == 0:
            return "import_failed", detail
        if session.imported == 0 and (
            session.skipped_duplicate + session.skipped_upstream_conflict > 0
        ):
            return "no_new_records", detail
    if tasks.get("failed", 0):
        return "index_failed", detail
    if tasks.get("processing", 0):
        return "index_processing", detail
    if tasks.get("pending", 0):
        return "index_queued", detail
    if total > 0:
        return "indexed", detail
    if live_records == 0 and session is not None and session.imported == 0:
        # 有会话、零新增、零任务（no_new_records 之外的兜底，如重复包回放）
        return "no_new_records", detail
    return "legacy_unknown", detail


def canonical_document_status(document_ids: list[str]) -> dict | None:
    """canonical-qa 按文档确认实际内容；不可达/异常 → None（如实 unknown）。

    返回 {document_id: {chunks, vector_ok, bm25_ok, entity_count,
    primary_section, ...}}（canonical /api/index/status.documents）。
    """
    base = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    if not base or not token or not document_ids:
        return None
    headers = {"X-TechDB-Index-Token": token}
    found: dict = {}
    remaining = list(dict.fromkeys(str(d) for d in document_ids if d))
    try:
        with httpx.Client(timeout=15.0) as client:
            # GET query 有长度上限：分批携带 document_ids
            while remaining:
                batch, remaining = remaining[:40], remaining[40:]
                r = client.get(
                    f"{base}/api/index/status",
                    params={"document_ids": ",".join(batch)},
                    headers=headers,
                )
                r.raise_for_status()
                docs = (r.json() or {}).get("documents") or {}
                found.update(docs)
        return found
    except (httpx.HTTPError, ValueError):
        return None


def upload_index_status(db: Session, record: UploadedFile) -> dict:
    """详情端点聚合：DB + 队列 + 会话 + canonical（真实可检索权威）。"""
    is_github = record.primary_section == "breadth" and record.breadth_source == "github"
    tasks = queue_aggregate(db, [record.id]).get(record.id, {})
    session = sessions_map(db, [record.id]).get(record.id)
    live_records = _record_count(db, record.id)

    result: dict = {
        "id": str(record.id),
        "filename": record.original_filename,
        "primary_section": record.primary_section,
        "breadth_source": record.breadth_source,
        "db": {
            "embedding_status": record.embedding_status,
            "chunk_count": record.chunk_count,
            "embedding_error": record.embedding_error,
        },
        "queue": {
            "total": sum(tasks.values()),
            **{k: tasks.get(k, 0) for k in ("done", "failed", "pending", "processing")},
        },
        "records": live_records,
        "index": None,
        "searchable": None,  # None = canonical 不可达，无法诚实判定
        "status": None,
    }

    if session is not None:
        result["session"] = {
            "package_date": session.package_date,
            "record_count": session.record_count,
            "imported": session.imported,
            "skipped_duplicate": session.skipped_duplicate,
            "skipped_upstream_conflict": session.skipped_upstream_conflict,
            "failed": session.failed,
            "package_deduplicated": bool(session.package_deduplicated),
            "replayed": bool(session.replayed),
        }

    if is_github or live_records > 0:
        # 行记录链（GitHub 增量包 / 逐行表格 / 行业·ATSC 表格）：
        # document_id = 行记录 id（非上传 id）——canonical 权威核对须逐记录进行。
        status, detail = map_github_status(record, tasks, session, live_records)
        result["status"] = status
        result["queue"].update({k: v for k, v in detail.items() if k.startswith("tasks_")})
        # canonical 权威确认：该上传名下存活记录的 document_id 逐个核对
        if live_records:
            record_ids = [
                str(row[0])
                for row in db.execute(
                    select(BreadthManualRecord.id).where(
                        BreadthManualRecord.upload_id == record.id
                    )
                ).all()
            ]
            docs = canonical_document_status(record_ids)
            if docs is None:
                result["index"] = {"error": "canonical_unreachable"}
            else:
                found = {did: d for did, d in docs.items()
                         if int(d.get("chunks") or 0) > 0}
                missing = [did for did in record_ids if did not in found]
                result["index"] = {
                    "documents_checked": len(record_ids),
                    "documents_found": len(found),
                    "documents_missing": len(missing),
                    "missing_document_ids": missing[:10],
                    "chunks": sum(int(d.get("chunks") or 0) for d in found.values()),
                    "vector_ok": sum(1 for d in found.values() if d.get("vector_ok")),
                    "bm25_ok": sum(1 for d in found.values() if d.get("bm25_ok")),
                    "unattributed": sum(
                        1 for d in found.values() if not d.get("primary_section")
                    ),
                }
                # Codex P1-3：部分缺失不算可检索——全部存活记录都在索引且
                # 逐文档 vector/bm25 健康才算 searchable（索引仍在写入时
                # 显示 index_processing，由 status 表达，不用 searchable 谎报）。
                result["searchable"] = (
                    bool(found)
                    and not missing
                    and all(d.get("vector_ok") and d.get("bm25_ok")
                            for d in found.values())
                )
                if status == "indexed" and (not found or missing
                                            or not result["searchable"]):
                    # 队列说 done 但索引有缺口（部分/全部丢失、向量或 BM25
                    # 不健康）——如实降级 legacy_unknown，重试=幂等重放恢复
                    result["status"] = "legacy_unknown"
        else:
            # 名下无存活记录：无可核对对象——不是错误，如实 0 文档不可检索
            result["index"] = {
                "documents_checked": 0,
                "documents_found": 0,
                "chunks": 0,
                "vector_ok": 0,
                "bm25_ok": 0,
                "unattributed": 0,
                "note": "no_live_records",
            }
            result["searchable"] = False
    else:
        # Docling 链（PDF 等文件级摄取）：document_id = 上传 id，同步写索引
        docs = canonical_document_status([str(record.id)])
        result["status"] = (
            "indexed" if record.embedding_status == "ready" else record.embedding_status
        )
        if docs is None:
            result["index"] = {"error": "canonical_unreachable"}
        else:
            d = docs.get(str(record.id)) or {}
            chunks = int(d.get("chunks") or 0)
            result["index"] = {
                "documents_found": 1 if chunks else 0,
                "chunks": chunks,
                "vector_ok": bool(d.get("vector_ok")),
                "bm25_ok": bool(d.get("bm25_ok")),
                "primary_section": d.get("primary_section"),
            }
            result["searchable"] = bool(
                chunks and d.get("vector_ok") and d.get("bm25_ok")
            )
            if record.embedding_status == "ready" and not chunks:
                # DB 说 ready 但索引没有——以 canonical 为准（1.1 契约）
                result["status"] = "legacy_unknown"
    return result

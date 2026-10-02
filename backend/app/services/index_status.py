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


def _route_state(*, executed: bool, ok_count: int, total: int,
                 error: str | None = None) -> dict:
    """任务一 1.1：单路（向量/关键词/图谱）状态契约。

    词汇：not_started / queued / processing / partial / complete / failed /
    unknown——单路失败绝不掩盖其他路（各路独立成态）。
    """
    if error == "canonical_unreachable":
        return {"state": "unknown", "reason": "canonical_unreachable"}
    if not executed:
        return {"state": "not_started", "reason": error or "no documents checked"}
    if total == 0:
        return {"state": "not_started", "reason": error or "no live documents"}
    if ok_count == total:
        return {"state": "complete", "reason": None}
    if ok_count == 0:
        return {"state": "failed", "reason": error or "0/%d documents healthy" % total}
    return {"state": "partial", "reason": error or "%d/%d documents healthy" % (ok_count, total)}


def upload_index_status(db: Session, record: UploadedFile) -> dict:
    """详情端点聚合（任务一 1.1 状态契约 + 1.3 摄取模式判定）。

    摄取模式按【真实链路特征】判定，不再用「有广度投影记录」猜测：
    - 行记录链（GitHub 增量包 / 逐行表格）：BreadthImportSession 存在或
      持久队列有任务——document_id = 行记录 id，canonical 逐记录核对；
    - 文档链（PDF 等 Docling 摄取，含行业/ATSC 勾选同步到广度的投影）：
      无会话无队列任务——document_id = 上传 id，同步写索引。历史缺陷：
      `is_github or live_records > 0` 把「同步到广度」的展示投影记录
      误判为行记录链，文件级索引永远不被核对 → documents_missing 误报。
    """
    is_github = record.primary_section == "breadth" and record.breadth_source == "github"
    tasks = queue_aggregate(db, [record.id]).get(record.id, {})
    session = sessions_map(db, [record.id]).get(record.id)
    queue_total = sum(tasks.values())
    live_records = _record_count(db, record.id)
    row_chain = is_github or session is not None or queue_total > 0

    result: dict = {
        "id": str(record.id),
        "filename": record.original_filename,
        "primary_section": record.primary_section,
        "breadth_source": record.breadth_source,
        "ingestion_mode": "row_records" if row_chain else "document",
        "db": {
            "embedding_status": record.embedding_status,
            "chunk_count": record.chunk_count,
            "embedding_error": record.embedding_error,
        },
        "queue": {
            "total": queue_total,
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

    if row_chain:
        # 行记录链：document_id = 行记录 id（非上传 id）
        status, detail = map_github_status(record, tasks, session, live_records)
        result["status"] = status
        result["queue"].update({k: v for k, v in detail.items() if k.startswith("tasks_")})
        if live_records:
            rows = db.execute(
                select(
                    BreadthManualRecord.id,
                    BreadthManualRecord.content_hash,
                    BreadthManualRecord.origin_section,
                    BreadthManualRecord.in_breadth_nav,
                ).where(BreadthManualRecord.upload_id == record.id)
            ).all()
            record_ids = [str(r[0]) for r in rows]
            expected_hashes = {str(r[0]): r[1] for r in rows}
            breadth_visible = any(bool(r[3]) for r in rows)
            origins = {str(r[2] or "breadth") for r in rows}
            docs = canonical_document_status(record_ids)
            if docs is None:
                result["index"] = {"error": "canonical_unreachable"}
                result["states"] = {
                    "breadth_visible": {
                        "state": "complete" if breadth_visible else "not_started",
                        "reason": None if breadth_visible else "无进广度导航的存活记录"},
                    "vector": _route_state(executed=False, ok_count=0, total=0,
                                           error="canonical_unreachable"),
                    "keyword": _route_state(executed=False, ok_count=0, total=0,
                                            error="canonical_unreachable"),
                    "graph": _route_state(executed=False, ok_count=0, total=0,
                                          error="canonical_unreachable"),
                }
            else:
                found = {did: d for did, d in docs.items()
                         if int(d.get("chunks") or 0) > 0}
                missing = [did for did in record_ids if did not in found]
                # 内容指纹核对（1.1）：DB 侧记录指纹必须仍在索引当前内容里
                # ——UPDATE 后索引若仍是旧世代，按身份对齐即暴露。
                hash_missing: list[str] = []
                for did, d in found.items():
                    expected = expected_hashes.get(did)
                    shas = d.get("content_shas") or []
                    if expected and shas and expected not in shas:
                        hash_missing.append(did)
                result["index"] = {
                    "documents_checked": len(record_ids),
                    "documents_found": len(found),
                    "documents_missing": len(missing),
                    "missing_document_ids": missing[:10],
                    "content_hash_missing": hash_missing[:10],
                    "chunks": sum(int(d.get("chunks") or 0) for d in found.values()),
                    "vector_ok": sum(1 for d in found.values() if d.get("vector_ok")),
                    "bm25_ok": sum(1 for d in found.values() if d.get("bm25_ok")),
                    "entity_count": sum(int(d.get("entity_count") or 0)
                                        for d in found.values()),
                    "primary_sections": sorted(origins),
                    "unattributed": sum(
                        1 for d in found.values() if not d.get("primary_section")),
                }
                total_docs = len(record_ids)
                vec_n = sum(1 for d in found.values() if d.get("vector_ok"))
                bm_n = sum(1 for d in found.values() if d.get("bm25_ok"))
                # 图谱（1.1）：增量图谱由存活 chunk 实时推导——chunk 在即
                # 「参与图谱构建」；无可抽取实体（entity_count=0）≠构建失败。
                graph_ok = len(found)
                # Codex#4：不把内部哨兵串 documents_missing 直接当用户面
                # reason——转为可读文案（缺哪些文档由 documents_missing 计数
                # 单独暴露，见 result["index"]）。
                graph_state = _route_state(
                    executed=True, ok_count=graph_ok, total=total_docs,
                    error=(f"有 {len(missing)} 篇文档未见于增量索引"
                           if missing else None))
                if not missing and graph_ok == total_docs and all(
                        int(d.get("entity_count") or 0) == 0 for d in found.values()):
                    graph_state["note"] = "无可抽取实体（不构成构建失败）"
                result["states"] = {
                    "breadth_visible": {
                        "state": "complete" if breadth_visible else "not_started",
                        "reason": None},
                    "vector": _route_state(
                        executed=len(found) > 0 or total_docs > 0,
                        ok_count=vec_n, total=total_docs,
                        error=None),
                    "keyword": _route_state(
                        executed=len(found) > 0 or total_docs > 0,
                        ok_count=bm_n, total=total_docs,
                        error=None),
                    "graph": graph_state,
                }
                # searchable（1.1）：三路全绿才可检索——向量+关键词+图谱参与
                # （chunk 全在即图谱参与；实体可为 0）。部分缺失/哈希错位/
                # 单路不健康都不可检索。
                result["searchable"] = (
                    bool(found)
                    and not missing
                    and not hash_missing
                    and vec_n == total_docs
                    and bm_n == total_docs
                    and graph_ok == total_docs
                )
                if status == "indexed" and not result["searchable"]:
                    # 队列说 done 但索引有缺口（部分/全部丢失、向量或 BM25
                    # 不健康、内容指纹错位）——如实降级，重试=幂等重放恢复
                    result["status"] = "legacy_unknown"
        else:
            # 名下无存活记录：无可核对对象——不是错误，如实 0 文档不可检索
            result["index"] = {
                "documents_checked": 0,
                "documents_found": 0,
                "chunks": 0,
                "vector_ok": 0,
                "bm25_ok": 0,
                "entity_count": 0,
                "unattributed": 0,
                "note": "no_live_records",
            }
            result["searchable"] = False
            result["states"] = {
                "breadth_visible": {"state": "not_started",
                                    "reason": "no_live_records"},
                "vector": _route_state(executed=False, ok_count=0, total=0,
                                       error="no_live_records"),
                "keyword": _route_state(executed=False, ok_count=0, total=0,
                                        error="no_live_records"),
                "graph": _route_state(executed=False, ok_count=0, total=0,
                                      error="no_live_records"),
            }
    else:
        # Docling 链（PDF 等文件级摄取，含行业/ATSC 同步到广度投影）：
        # document_id = 上传 id，同步写索引
        docs = canonical_document_status([str(record.id)])
        result["status"] = (
            "indexed" if record.embedding_status == "ready" else record.embedding_status
        )
        breadth_visible = (record.primary_section == "breadth"
                           or bool(getattr(record, "sync_breadth", False)))
        if docs is None:
            result["index"] = {"error": "canonical_unreachable"}
            result["states"] = {
                "breadth_visible": {
                    "state": "complete" if breadth_visible else "not_started",
                    "reason": None},
                "vector": _route_state(executed=False, ok_count=0, total=0,
                                       error="canonical_unreachable"),
                "keyword": _route_state(executed=False, ok_count=0, total=0,
                                        error="canonical_unreachable"),
                "graph": _route_state(executed=False, ok_count=0, total=0,
                                      error="canonical_unreachable"),
            }
        else:
            d = docs.get(str(record.id)) or {}
            chunks = int(d.get("chunks") or 0)
            vec_ok = bool(d.get("vector_ok"))
            bm_ok = bool(d.get("bm25_ok"))
            expected = record.checksum_sha256
            shas = d.get("content_shas") or []
            hash_ok = (not expected or not shas) or (expected in shas)
            result["index"] = {
                "documents_found": 1 if chunks else 0,
                "chunks": chunks,
                "vector_ok": vec_ok,
                "bm25_ok": bm_ok,
                "entity_count": int(d.get("entity_count") or 0),
                "primary_section": d.get("primary_section"),
                "content_hash_ok": bool(hash_ok),
            }
            def _doc_route(ok: bool) -> dict:
                if not chunks:
                    return {"state": "not_started",
                            "reason": "索引无该文档 chunk"}
                return {"state": "complete" if ok else "failed",
                        "reason": None if ok else "健康校验未通过"}
            graph_state = _doc_route(chunks > 0)
            if chunks and int(d.get("entity_count") or 0) == 0:
                graph_state["note"] = "无可抽取实体（不构成构建失败）"
            result["states"] = {
                "breadth_visible": {
                    "state": "complete" if breadth_visible else "not_started",
                    "reason": None},
                "vector": _doc_route(vec_ok),
                "keyword": _doc_route(bm_ok),
                "graph": graph_state,
            }
            result["searchable"] = bool(chunks and vec_ok and bm_ok and hash_ok)
            if record.embedding_status == "ready" and not result["searchable"]:
                # DB 说 ready 但索引没有/不健康/指纹错位——以 canonical 为准
                result["status"] = "legacy_unknown"
    return result

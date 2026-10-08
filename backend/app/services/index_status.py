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


def _verified_document_routes(doc: dict, expected_hash: str | None,
                              origin: str, *, row_mode: bool) -> dict:
    """Validate identity/version before trusting any individual route's health."""
    routes = {"vector": "vector_ok", "keyword": "bm25_ok", "graph": "graph_ok"}
    if not int(doc.get("chunks") or 0):
        return {r: {"state": "not_started", "reason": "索引尚无该文档"} for r in routes}
    issue, issue_state = None, "unknown"
    shas = doc.get("content_shas") or []
    actual_hashes = shas if row_mode else (
        [doc["checksum_sha256"]] if doc.get("checksum_sha256") else shas)
    scopes = doc.get("primary_sections") or [doc.get("primary_section")]
    if not expected_hash or not actual_hashes:
        issue = "内容指纹缺失，尚不能确认索引版本"
    elif set(actual_hashes) != {expected_hash}:
        issue, issue_state = "索引内容版本与当前资料不一致", "failed"
    elif row_mode and doc.get("content_sha_rows", doc["chunks"]) != doc["chunks"]:
        issue = "部分分块缺少内容指纹"
    if not all(scopes):
        issue = issue or "索引缺少原始来源归属"
    elif set(scopes) != {origin}:
        issue, issue_state = "索引来源归属与当前资料不一致", "failed"
    if doc.get("live_chunks", doc["chunks"]) != doc["chunks"]:
        issue, issue_state = "索引记录已被屏蔽或正在变更", "failed"
    result = {}
    for route, health_key in routes.items():
        health = doc.get(health_key)
        if issue:
            result[route] = {"state": issue_state, "reason": issue}
        elif health is None:
            result[route] = {"state": "unknown", "reason": "服务未提供该路健康校验"}
        else:
            result[route] = {"state": "complete" if health else "failed",
                             "reason": None if health else (doc.get("graph_error")
                                        if route == "graph" else "健康校验未通过")}
    if result["graph"]["state"] == "complete" and not doc.get("entity_count"):
        result["graph"]["note"] = "无可抽取实体（不构成构建失败）"
    return result


def _apply_verified_states(result: dict, docs: dict, identities: dict,
                           *, row_mode: bool) -> None:
    per_doc = [_verified_document_routes(docs.get(did) or {}, fingerprint, origin,
                                        row_mode=row_mode)
               for did, (fingerprint, origin) in identities.items()]
    waiting = ("processing" if result["queue"].get("processing") else
               "queued" if result["queue"].get("pending") else None)
    if result["queue"].get("failed"):
        waiting = None
    for route in ("vector", "keyword", "graph"):
        states = [d[route] for d in per_doc]
        complete = sum(d["state"] == "complete" for d in states)
        if complete == len(states) and states:
            value = {"state": "complete", "reason": None}
            if route == "graph" and all(d.get("note") for d in states):
                value["note"] = states[0]["note"]
        elif waiting:
            value = {"state": waiting, "reason": f"当前版本已确认 {complete}/{len(states)} 篇"}
        elif complete:
            value = {"state": "partial", "reason": f"当前版本已确认 {complete}/{len(states)} 篇"}
        else:
            value = next((d for d in states if d["state"] == "failed"), None)
            value = value or next((d for d in states if d["state"] == "unknown"), None)
            value = value or {"state": "not_started", "reason": "索引尚无当前版本文档"}
        result["states"][route] = value
    route_states = [result["states"][r]["state"] for r in ("vector", "keyword", "graph")]
    result["searchable"] = (True if all(s == "complete" for s in route_states)
                            else None if "unknown" in route_states and not any(
                                s in ("failed", "partial", "queued", "processing", "not_started")
                                for s in route_states) else False)
    if result["status"] == "indexed" and result["searchable"] is not True:
        result["status"] = "legacy_unknown"
    result["retryable"] = result["status"] in (
        "legacy_unknown", "index_failed", "import_failed", "failed")


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
                result["states"] = {}
                _apply_verified_states(result, docs, {
                    str(r[0]): (r[1], str(r[2] or "breadth")) for r in rows
                }, row_mode=True)
                visible = sum(bool(r[3]) for r in rows)
                result["states"]["breadth_visible"] = {
                    "state": "complete" if visible == len(rows) else "partial" if visible else "not_started",
                    "reason": None if visible == len(rows) else f"已显示 {visible}/{len(rows)} 条",
                }
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
        breadth_visible = bool(live_records and db.scalar(
            select(func.count()).select_from(BreadthManualRecord).where(
                BreadthManualRecord.upload_id == record.id,
                BreadthManualRecord.in_breadth_nav.is_(True))))
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
            hash_ok = bool(expected and (d.get("checksum_sha256") == expected
                                       or set(shas) == {expected}))
            result["index"] = {
                "documents_found": 1 if chunks else 0,
                "chunks": chunks,
                "vector_ok": vec_ok,
                "bm25_ok": bm_ok,
                "entity_count": int(d.get("entity_count") or 0),
                "primary_section": d.get("primary_section"),
                "content_hash_ok": bool(hash_ok),
            }
            result["states"] = {
                "breadth_visible": {
                    "state": "complete" if breadth_visible else "not_started", "reason": None}}
            _apply_verified_states(result, docs, {
                str(record.id): (record.checksum_sha256, record.primary_section or "breadth")
            }, row_mode=False)
    # A completed queue is not evidence of a healthy, current index.
    if result["status"] == "indexed" and result["searchable"] is not True:
        result["status"] = "legacy_unknown"
    result["retryable"] = result["status"] in (
        "legacy_unknown", "index_failed", "import_failed", "failed")
    return result

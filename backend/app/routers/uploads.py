from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.classification import CONFIDENTIALITY_LEVELS, normalize_confidentiality
from app.core.security import get_current_user, require_admin
from app.db.session import get_db
from app.models.uploaded_file import UploadedFile
from app.services.upload_ingestion import (
    SOURCE_TYPES,
    StoredUpload,
    UploadValidationError,
    classification_status_for,
    ensure_extractable,
    load_taxonomy,
    persist_upload,
    process_uploaded_file,
    remove_stored_upload,
    safe_upload_path,
    validate_filename,
)


router = APIRouter(tags=["uploads"])


class ClassificationOverride(BaseModel):
    primary_category: str
    secondary_categories: list[str] = Field(default_factory=list, max_length=3)
    reason: str | None = Field(default=None, max_length=2000)


def _serialize(record: UploadedFile) -> dict:
    terminal = {"classified", "unclassified", "irrelevant", "legacy_unclassified"}
    if record.storage_status != "stored":
        ingestion_status = record.storage_status
    elif record.classification_status not in terminal:
        ingestion_status = record.classification_status
    elif record.embedding_status == "ready":
        ingestion_status = "ready"
    elif record.embedding_status == "skipped":
        ingestion_status = "embedding_skipped"
    else:
        ingestion_status = f"embedding_{record.embedding_status}"
    return {
        "id": str(record.id),
        "original_filename": record.original_filename,
        "stored_filename": record.stored_filename,
        "title": record.title,
        "confidentiality": record.confidentiality,
        "source_type": record.source_type,
        "domain_refs": record.domain_refs or [],
        "note": record.note,
        "title_source": record.title_source,
        "mime_type": record.mime_type,
        "size_bytes": record.size_bytes,
        "checksum_sha256": record.checksum_sha256,
        "storage_status": record.storage_status,
        "taxonomy_version": record.taxonomy_version,
        "primary_category": record.primary_category,
        "secondary_categories": record.secondary_categories or [],
        "classification_status": record.classification_status,
        "classification_confidence": record.classification_confidence,
        "classification_source": record.classification_source,
        "classification_reason": record.classification_reason,
        "classification_error": record.classification_error,
        "classification_attempts": record.classification_attempts,
        "classified_at": record.classified_at.isoformat() if record.classified_at else None,
        "embedding_status": record.embedding_status,
        "embedding_model": record.embedding_model,
        "embedding_dim": record.embedding_dim,
        "embedding_error": record.embedding_error,
        "embedding_attempts": record.embedding_attempts,
        "chunk_count": record.chunk_count,
        "embedded_at": record.embedded_at.isoformat() if record.embedded_at else None,
        "ingestion_status": ingestion_status,
        "submitted_by": record.submitted_by,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def _uuid_or_400(file_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(file_id)
    except ValueError as exc:
        raise HTTPException(400, "无效的文件 ID") from exc


def _validate_category(primary: str, secondary: list[str] | None = None) -> tuple[str, list[str]]:
    taxonomy = load_taxonomy()
    if primary not in taxonomy.categories:
        raise HTTPException(400, "主分类不在当前广度追踪分类目录中")
    cleaned: list[str] = []
    for value in secondary or []:
        if value not in taxonomy.business_categories:
            raise HTTPException(400, f"辅助分类不是业务分类：{value}")
        if value != primary and value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > 3:
        raise HTTPException(400, "辅助分类最多 3 个")
    return primary, cleaned


@router.get("/uploads/taxonomy")
def get_upload_taxonomy(current_user: str = Depends(get_current_user)) -> dict:
    taxonomy = load_taxonomy()
    return {
        "taxonomy_id": taxonomy.taxonomy_id,
        "taxonomy_version": taxonomy.version,
        "output_count": len(taxonomy.categories),
        "business_category_count": len(taxonomy.business_categories),
        "business_categories": taxonomy.business_categories,
        "result_labels": taxonomy.result_labels,
        "categories": taxonomy.categories,
    }


@router.post("/uploads", status_code=201)
async def upload_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    title: str | None = Form(None),
    confidentiality: str | None = Form(None),
    source_type: str | None = Form(None),
    note: str | None = Form(None),
    primary_category: str | None = Form(None),
    current_user: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if not files:
        raise HTTPException(400, "未提供文件")
    if title and len(files) > 1:
        raise HTTPException(400, "批量上传不能共用标题，请留空让系统逐文件生成")
    try:
        confidentiality = normalize_confidentiality(confidentiality)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if source_type and source_type not in SOURCE_TYPES:
        raise HTTPException(400, f"来源类型只能是：{', '.join(sorted(SOURCE_TYPES))}")

    for upload in files:
        try:
            validate_filename(upload.filename or "")
        except UploadValidationError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

    taxonomy = load_taxonomy()
    manual_category = None
    if primary_category:
        manual_category, _ = _validate_category(primary_category)

    stored_items: list[StoredUpload] = []
    records: list[UploadedFile] = []
    try:
        for upload in files:
            stored = await persist_upload(upload)
            stored_items.append(stored)

            original_filename = upload.filename or stored.path.name
            # 上传即校验：提取不出文本的文件直接拒绝并告知原因（不再落库为"未分类"）。
            ensure_extractable(stored.path, original_filename)
            manual_title = title.strip() if title and title.strip() else None
            fallback_title = stored.path.stem if not original_filename else original_filename.rsplit(".", 1)[0]
            record = UploadedFile(
                stored_filename=stored.stored_filename,
                original_filename=original_filename,
                mime_type=upload.content_type,
                size_bytes=stored.size_bytes,
                checksum_sha256=stored.checksum_sha256,
                storage_status="stored",
                title=manual_title or fallback_title,
                confidentiality=confidentiality,
                source_type=source_type,
                domain_refs=None,
                note=note,
                title_source="manual" if manual_title else "filename_fallback",
                taxonomy_version=taxonomy.version if manual_category else None,
                primary_category=manual_category,
                secondary_categories=[],
                classification_status=(
                    classification_status_for(manual_category) if manual_category else "pending"
                ),
                classification_confidence=1.0 if manual_category else None,
                classification_source="manual" if manual_category else None,
                classification_reason="上传时由管理员指定" if manual_category else None,
                classified_at=datetime.now(timezone.utc) if manual_category else None,
                submitted_by=current_user,
            )
            db.add(record)
            records.append(record)
        db.commit()
        for record in records:
            db.refresh(record)
    except UploadValidationError as exc:
        db.rollback()
        for stored in stored_items:
            remove_stored_upload(stored)
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception:
        db.rollback()
        for stored in stored_items:
            remove_stored_upload(stored)
        raise

    for record in records:
        background_tasks.add_task(process_uploaded_file, str(record.id))
    return {"count": len(records), "files": [_serialize(record) for record in records]}


@router.get("/uploads")
def list_uploads(
    source_type: str | None = None,
    primary_category: str | None = None,
    classification_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    filters = []
    if source_type:
        filters.append(UploadedFile.source_type == source_type)
    if primary_category:
        filters.append(UploadedFile.primary_category == primary_category)
    if classification_status:
        filters.append(UploadedFile.classification_status == classification_status)

    query = select(UploadedFile).where(*filters).order_by(UploadedFile.created_at.desc())
    count_query = select(func.count()).select_from(UploadedFile).where(*filters)
    rows = db.scalars(query.limit(max(1, min(limit, 500))).offset(max(0, offset))).all()
    return {"count": db.scalar(count_query) or 0, "files": [_serialize(row) for row in rows]}


@router.post("/uploads/{file_id}/classification/retry", status_code=202)
def retry_upload_classification(
    file_id: str,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(UploadedFile, _uuid_or_400(file_id))
    if record is None:
        raise HTTPException(404, "文件不存在")
    if record.storage_status != "stored":
        raise HTTPException(409, "文件未正常落盘，不能重试分类")
    if record.classification_status in {"pending", "processing"}:
        return {"id": str(record.id), "classification_status": record.classification_status}
    record.classification_status = "pending"
    record.classification_error = None
    record.embedding_status = "pending"
    record.embedding_error = None
    record.embedded_at = None
    record.chunk_count = 0
    db.commit()
    background_tasks.add_task(process_uploaded_file, str(record.id))
    return {"id": str(record.id), "classification_status": "pending"}


@router.post("/uploads/{file_id}/embedding/retry", status_code=202)
def retry_upload_embedding(
    file_id: str,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(UploadedFile, _uuid_or_400(file_id))
    if record is None:
        raise HTTPException(404, "文件不存在")
    if record.storage_status != "stored":
        raise HTTPException(409, "文件未正常落盘，不能重试 embedding")
    terminal = {"classified", "unclassified", "irrelevant", "legacy_unclassified"}
    if record.classification_status not in terminal:
        raise HTTPException(409, "请先完成文件分类")
    if record.embedding_status in {"pending", "processing"}:
        return {"id": str(record.id), "embedding_status": record.embedding_status}
    record.embedding_status = "pending"
    record.embedding_error = None
    record.embedded_at = None
    record.chunk_count = 0
    db.commit()
    background_tasks.add_task(process_uploaded_file, str(record.id))
    return {"id": str(record.id), "embedding_status": "pending"}


@router.put("/uploads/{file_id}/classification")
def override_upload_classification(
    file_id: str,
    payload: ClassificationOverride,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    record = db.get(UploadedFile, _uuid_or_400(file_id))
    if record is None:
        raise HTTPException(404, "文件不存在")
    if record.storage_status != "stored":
        raise HTTPException(409, "文件未正常落盘，不能人工分类")
    primary, secondary = _validate_category(payload.primary_category, payload.secondary_categories)
    taxonomy = load_taxonomy()
    record.taxonomy_version = taxonomy.version
    record.primary_category = primary
    record.secondary_categories = secondary
    record.classification_status = classification_status_for(primary)
    record.classification_confidence = 1.0
    record.classification_source = "manual"
    record.classification_reason = payload.reason or "管理员人工修正"
    record.classification_error = None
    record.classified_at = datetime.now(timezone.utc)
    record.embedding_status = "pending"
    record.embedding_error = None
    record.embedded_at = None
    record.chunk_count = 0
    db.commit()
    db.refresh(record)
    background_tasks.add_task(process_uploaded_file, str(record.id))
    return _serialize(record)


@router.get("/uploads/{file_id}/download")
def download_upload(
    file_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    record = db.get(UploadedFile, _uuid_or_400(file_id))
    if record is None:
        raise HTTPException(404, "文件不存在")

    try:
        path = safe_upload_path(record.stored_filename)
    except ValueError as exc:
        raise HTTPException(500, "文件存储键无效") from exc
    if not path.is_file():
        record.storage_status = "missing"
        db.commit()
        raise HTTPException(410, "文件已被移除")

    def iterfile():
        with open(path, "rb") as handle:
            while chunk := handle.read(64 * 1024):
                yield chunk

    safe_name = record.original_filename.replace("\r", " ").replace("\n", " ")
    quoted_name = quote(safe_name, safe="")
    return StreamingResponse(
        iterfile(),
        media_type=record.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_name}",
            "Content-Length": str(record.size_bytes),
        },
    )

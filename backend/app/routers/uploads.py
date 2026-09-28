from __future__ import annotations

import logging
import subprocess
import tempfile
import uuid

import httpx
from datetime import datetime, timezone
from pathlib import Path
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
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_admin, require_upload
from app.db.session import get_db
from app.models.index_task import IndexTask
from app.services.table_rows import (
    TableParseError,
    ALLOWED_SUFFIXES as ROW_MODE_SUFFIXES,
    import_rows,
    parse_table,
    preview as preview_table,
    validate_mapping,
)
from app.models.uploaded_file import UploadedFile
from app.services.github_import import (
    GitHubPackageError,
    import_github_package,
    note_for_counts,
    validate_github_filename,
)
from app.services.upload_ingestion import (
    StoredUpload,
    UploadValidationError,
    classification_status_for,
    delete_uploaded_file,
    load_taxonomy,
    normalize_document_date,
    rename_uploaded_file,
    persist_upload,
    process_uploaded_file,
    remove_stored_upload,
    safe_upload_path,
    taxonomy_tree_paths,
    validate_filename,
)

PRIMARY_SECTIONS = {"breadth", "industry", "atsc"}
BREADTH_SOURCES = {"github", "other"}


def _validate_section_combo(primary_section: str | None, breadth_source: str | None) -> tuple[str, str | None]:
    """校验分区组合：广度必须给出来源；非广度不允许来源。"""
    section = (primary_section or "industry").strip()
    if section not in PRIMARY_SECTIONS:
        raise HTTPException(400, "一级分区只能是：breadth / industry / atsc")
    source = (breadth_source or "").strip() or None
    if section == "breadth":
        if source not in BREADTH_SOURCES:
            raise HTTPException(400, "广度追踪必须选择二级来源：github（GitHub广度情报）或 other（其他广度情报）")
    elif source is not None:
        raise HTTPException(400, "仅广度追踪可以选择二级来源")
    return section, source


router = APIRouter(tags=["uploads"])

logger = logging.getLogger(__name__)

OFFICE_PREVIEW_EXTS = {".ppt", ".pptx", ".doc", ".docx", ".odp", ".odt", ".ods", ".xls", ".xlsx"}


def _render_pdf_first_page(pdf_path: Path, out_png: Path, scale: float = 1.6) -> None:
    """用 pypdfium2 把 PDF 第一页渲染为 PNG（Docling 同源依赖，无需额外安装）。"""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        bitmap = doc[0].render(scale=scale)
        image = bitmap.to_pil()
    finally:
        doc.close()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_png, format="PNG")


def _convert_office_first_page(original: Path, out_png: Path) -> None:
    """LibreOffice 无头模式把 Office 文档转 PDF，再渲染第一页。"""
    with tempfile.TemporaryDirectory(prefix="techdb-preview-") as tmp:
        subprocess.run(
            [
                "soffice", "--headless",
                "-env:UserInstallation=file://" + tmp + "/lo",
                "--convert-to", "pdf", "--outdir", tmp, str(original),
            ],
            check=True,
            timeout=120,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        converted = Path(tmp) / (original.stem + ".pdf")
        if not converted.is_file():
            raise RuntimeError("LibreOffice 未产出 PDF")
        _render_pdf_first_page(converted, out_png)


class ClassificationOverride(BaseModel):
    primary_category: str
    secondary_categories: list[str] = Field(default_factory=list, max_length=3)
    reason: str | None = Field(default=None, max_length=2000)


def _serialize(record: UploadedFile) -> dict:
    terminal = {"classified", "unclassified", "irrelevant", "legacy_unclassified"}
    if record.primary_section == "breadth" and record.breadth_source == "github":
        # 增量包不是文档：不走 Docling/索引摄取，状态只表达导入结果
        ingestion_status = "imported"
    elif record.storage_status != "stored":
        ingestion_status = record.storage_status
    elif record.embedding_status == "processing" and not record.document_assets:
        ingestion_status = "document_processing"
    elif record.classification_status not in terminal:
        ingestion_status = record.classification_status
    elif record.embedding_status == "ready":
        ingestion_status = "ready"
    elif record.embedding_status == "skipped":
        ingestion_status = "embedding_skipped"
    elif record.embedding_status == "queued":
        ingestion_status = "index_queued"
    else:
        ingestion_status = f"embedding_{record.embedding_status}"
    return {
        "id": str(record.id),
        "document_id": str(record.id),
        "filename": record.original_filename,
        "chunks_count": record.chunk_count,
        "status": ingestion_status,
        "document_assets": record.document_assets,
        "original_filename": record.original_filename,
        "stored_filename": record.stored_filename,
        "title": record.title,
        "primary_section": record.primary_section,
        "breadth_source": record.breadth_source,
        "domain_refs": record.domain_refs or [],
        "note": record.note,
        "title_source": record.title_source,
        "mime_type": record.mime_type,
        # 资料日期（管理员填写，YYYY-MM-DD 或空）
        "document_date": record.document_date,
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
    if primary == "未分类":
        # 语义约定：未分类只表示"尚未分类"，不能作为人工指定的分类结果。
        raise HTTPException(400, "未分类仅表示尚未分类，不能人工指定；请选择具体分类或不相关")
    if primary != "不相关" and primary not in taxonomy_tree_paths(taxonomy):
        # 人工指定节点可以是树上任意节点（含非叶子）；不相关是合法的树外结果。
        raise HTTPException(400, "所选行业图景节点不存在")
    cleaned: list[str] = []
    for value in secondary or []:
        if value not in taxonomy.business_categories:
            raise HTTPException(400, f"辅助分类不是业务分类：{value}")
        if value != primary and value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > 3:
        raise HTTPException(400, "辅助分类最多 3 个")
    return primary, cleaned


@router.get("/uploads/formats")
def get_upload_formats(current_user: str = Depends(get_current_user)) -> dict:
    from app.document_ingestion.parser import supported_formats
    return supported_formats()


@router.get("/uploads/{file_id}/assets/{asset}")
def download_document_asset(file_id: str, asset: str,
                            current_user: str = Depends(require_upload),
                            db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    record = db.get(UploadedFile, _uuid_or_400(file_id))
    if record is None:
        raise HTTPException(404, "资料不存在")
    names = {"markdown": "document.md", "docling_json": "document.json",
             "chunks": "chunks.jsonl", "chunk_metadata": "chunk_metadata.jsonl",
             "manifest": "manifest.json", "conversion": "conversion.json"}
    if asset not in names or not record.document_assets:
        raise HTTPException(404, "文档资产尚未生成")
    path = safe_upload_path(record.document_assets["bundle"] + "/" + names[asset])
    if not path.is_file():
        raise HTTPException(404, "文档资产不存在，请重试解析")
    return FileResponse(path, filename=names[asset], media_type="application/octet-stream")


@router.get("/uploads/{file_id}/preview")
def upload_file_preview(
    file_id: str,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """资料首页预览：PDF/Office 渲染第一页为 PNG（结果缓存在资产包），图片直接返回原件。"""
    record = db.get(UploadedFile, _uuid_or_400(file_id))
    if record is None or record.storage_status != "stored":
        raise HTTPException(404, "资料不存在")
    try:
        original = safe_upload_path(record.stored_filename)
    except ValueError as exc:
        raise HTTPException(500, "文件存储键无效") from exc
    if not original.is_file():
        raise HTTPException(410, "文件已被移除")

    preview_path = None
    bundle = str((record.document_assets or {}).get("bundle") or "")
    if bundle:
        try:
            candidate = safe_upload_path(bundle + "/preview_page1.png")
            if candidate.is_file():
                return FileResponse(candidate, media_type="image/png")
            preview_path = candidate
        except ValueError:
            preview_path = None

    mime = (record.mime_type or "").lower()
    suffix = original.suffix.lower()

    if mime.startswith("image/"):
        return FileResponse(original, media_type=mime or "image/png")

    if preview_path is None:
        raise HTTPException(404, "该资料缺少资产包，无法生成预览")

    try:
        if mime == "application/pdf" or suffix == ".pdf":
            _render_pdf_first_page(original, preview_path)
        elif suffix in OFFICE_PREVIEW_EXTS:
            _convert_office_first_page(original, preview_path)
        else:
            raise HTTPException(404, "该资料类型暂不支持预览")
    except HTTPException:
        raise
    except Exception:
        logger.warning("资料首页预览生成失败: %s", file_id, exc_info=True)
        raise HTTPException(404, "无法生成首页预览，请稍后重试")
    return FileResponse(preview_path, media_type="image/png")


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
        "all_paths": taxonomy_tree_paths(taxonomy),
    }


@router.post("/uploads/row-preview")
async def upload_row_preview(
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
    current_user: str = Depends(require_upload),
) -> dict:
    """表格逐行模式预览：返回工作表/表头/前 20 行，供前端做列映射。"""
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in ROW_MODE_SUFFIXES:
        raise HTTPException(400, "逐行模式只支持 .xlsx / .csv")
    data = await file.read()
    if len(data) > 64 * 1024 * 1024:
        raise HTTPException(400, "表格文件过大（>64MB），请拆分后上传")
    try:
        return preview_table(data, file.filename or "", sheet)
    except TableParseError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/uploads", status_code=201)
async def upload_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    title: str | None = Form(None),
    note: str | None = Form(None),
    primary_section: str | None = Form(None),
    breadth_source: str | None = Form(None),
    primary_category: str | None = Form(None),
    document_date: str | None = Form(None),
    row_mode: bool = Form(False),
    column_mapping: str | None = Form(None),
    sheet: str | None = Form(None),
    sync_upload_to_breadth: bool = Form(False),
    current_user: str = Depends(require_upload),
    db: Session = Depends(get_db),
) -> dict:
    if not files:
        raise HTTPException(400, "未提供文件")
    if title and len(files) > 1:
        raise HTTPException(400, "批量上传不能共用标题，请留空让系统逐文件生成")

    section, bsource = _validate_section_combo(primary_section, breadth_source)
    if sync_upload_to_breadth and section not in ("industry", "atsc"):
        raise HTTPException(400, "同步上传到广度情报仅适用于行业追踪 / ATSC 内部报告")

    # ── GitHub广度情报：daily/YYYY-MM-DD.zip 增量包导入通道 ──
    # 一个包一次上传（单文件），同步解包导入并返回契约计数；不走 Docling 摄取。
    if section == "breadth" and bsource == "github":
        if len(files) != 1:
            raise HTTPException(400, "GitHub 增量包一次只上传一个 daily/YYYY-MM-DD.zip")
        upload = files[0]
        try:
            validate_github_filename(upload.filename or "")
        except GitHubPackageError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            stored = await persist_upload(upload, allowed_suffixes={".zip"})
        except UploadValidationError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        try:
            record = UploadedFile(
                stored_filename=stored.stored_filename,
                original_filename=upload.filename or stored.path.name,
                mime_type=upload.content_type or "application/zip",
                checksum_sha256=stored.checksum_sha256,
                storage_status="stored",
                title=None,
                domain_refs=None,
                note=note,
                document_date=None,
                primary_section=section,
                breadth_source=bsource,
                title_source="manual",
                taxonomy_version=None,
                primary_category=None,
                secondary_categories=[],
                classification_status="classified",
                classification_confidence=1.0,
                classification_source="manual",
                classification_reason="GitHub 增量包导入（不做文档分类）",
                classified_at=datetime.now(timezone.utc),
                # queued：导入产生 breadth_index_tasks，后台 worker 写 canonical-qa
                embedding_status="queued",
                embedding_error=None,
                submitted_by=current_user,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            payload = import_github_package(db, record, stored.path)
            # 包日期回填标题/资料日期与计数摘要（幂等重放也走这里）
            record.title = f"广度增量包 {payload['package_date']}"
            record.document_date = payload["package_date"]
            record.note = note_for_counts(payload)
            db.commit()
            db.refresh(record)
            return {
                "count": 1,
                "files": [_serialize(record)],
                "github_import": payload,
            }
        except GitHubPackageError as exc:
            # 包不合规：已提交的 uploaded_files 行必须一并清掉，避免孤儿记录
            db.rollback()
            db.execute(sa_delete(UploadedFile).where(UploadedFile.id == record.id))
            db.execute(sa_delete(IndexTask).where(IndexTask.upload_id == record.id))
            db.commit()
            remove_stored_upload(stored)
            raise HTTPException(400, f"增量包不合规：{exc}") from exc
        except Exception:
            db.rollback()
            db.execute(sa_delete(UploadedFile).where(UploadedFile.id == record.id))
            db.execute(sa_delete(IndexTask).where(IndexTask.upload_id == record.id))
            db.commit()
            remove_stored_upload(stored)
            raise

    # ── 表格逐行模式（六节）：xlsx/csv 每行一个情报，不走 Docling ──
    if row_mode:
        # manual_category 在通用路径（下方 514 行）才赋值；逐行分支
        # 也引用它（行分类的 fallback），必须先初始化
        manual_category = None
        if primary_category:
            manual_category, _ = _validate_category(primary_category)
        try:
            document_date = normalize_document_date(document_date)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if len(files) != 1:
            raise HTTPException(400, "逐行模式一次上传一个表格文件")
        if section == "breadth" and bsource == "github":
            raise HTTPException(400, "逐行模式不适用于 GitHub 增量包通道")
        suffix = "." + (files[0].filename or "").rsplit(".", 1)[-1].lower() if "." in (files[0].filename or "") else ""
        if suffix not in ROW_MODE_SUFFIXES:
            raise HTTPException(400, "逐行模式只支持 .xlsx / .csv")
        try:
            mapping = validate_mapping(column_mapping)
        except TableParseError as exc:
            raise HTTPException(400, str(exc)) from exc
        upload = files[0]
        try:
            stored = await persist_upload(upload, allowed_suffixes=ROW_MODE_SUFFIXES)
        except UploadValidationError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        try:
            data = stored.path.read_bytes()
            sheets = parse_table(data, upload.filename or "", sheet)
            fallback_title = (upload.filename or stored.path.name).rsplit(".", 1)[0]
            record = UploadedFile(
                stored_filename=stored.stored_filename,
                original_filename=upload.filename or stored.path.name,
                mime_type=upload.content_type,
                checksum_sha256=stored.checksum_sha256,
                storage_status="stored",
                title=title.strip() if title and title.strip() else f"表格情报 {fallback_title}",
                domain_refs=None,
                note=note,
                document_date=document_date,
                primary_section=section,
                breadth_source=bsource,
                title_source="manual" if title and title.strip() else "filename_fallback",
                taxonomy_version=None,
                primary_category=manual_category,
                secondary_categories=[],
                # 行数据逐条分类来自映射列，文件级 AI 分类/嵌入不适用
                classification_status="classified",
                classification_confidence=1.0,
                classification_source="manual",
                classification_reason="表格逐行导入（行级分类取自映射列）",
                classified_at=datetime.now(timezone.utc),
                # queued：行记录入队持久索引任务，后台写 canonical-qa
                embedding_status="queued",
                submitted_by=current_user,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            stats = import_rows(
                db, record, sheets, mapping,
                fallback_date=document_date,
                category_fallback=manual_category,
            )
            record.note = (
                f"逐行导入 {stats['imported']} 条"
                + (f" · 空标题跳过 {stats['skipped_empty']}" if stats["skipped_empty"] else "")
                + (f" · 去重跳过 {stats['skipped_duplicate']}" if stats["skipped_duplicate"] else "")
            )
            db.commit()
            db.refresh(record)
            return {
                "count": 1,
                "files": [_serialize(record)],
                "row_import": stats,
            }
        except TableParseError as exc:
            db.rollback()
            db.execute(sa_delete(UploadedFile).where(UploadedFile.id == record.id))
            db.execute(sa_delete(IndexTask).where(IndexTask.upload_id == record.id))
            db.commit()
            remove_stored_upload(stored)
            raise HTTPException(400, f"表格解析失败：{exc}") from exc
        except Exception:
            db.rollback()
            db.execute(sa_delete(UploadedFile).where(UploadedFile.id == record.id))
            db.execute(sa_delete(IndexTask).where(IndexTask.upload_id == record.id))
            db.commit()
            remove_stored_upload(stored)
            raise

    for upload in files:
        try:
            validate_filename(upload.filename or "", upload.content_type)
        except UploadValidationError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

    taxonomy = load_taxonomy()
    manual_category = None
    if primary_category:
        manual_category, _ = _validate_category(primary_category)
    try:
        document_date = normalize_document_date(document_date)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    stored_items: list[StoredUpload] = []
    records: list[UploadedFile] = []
    try:
        for upload in files:
            stored = await persist_upload(upload)
            stored_items.append(stored)

            original_filename = upload.filename or stored.path.name
            # Conversion/OCR runs once in the durable background ingestion path.
            manual_title = title.strip() if title and title.strip() else None
            fallback_title = stored.path.stem if not original_filename else original_filename.rsplit(".", 1)[0]
            record = UploadedFile(
                stored_filename=stored.stored_filename,
                original_filename=original_filename,
                mime_type=upload.content_type,
                checksum_sha256=stored.checksum_sha256,
                storage_status="stored",
                title=manual_title or fallback_title,
                domain_refs=None,
                note=note,
                document_date=document_date,
                primary_section=section,
                breadth_source=bsource,
                # 行业追踪/ATSC：勾选后广度追踪保留一条指向本资料的记录
                sync_breadth=sync_upload_to_breadth,
                title_source="manual" if manual_title else "filename_fallback",
                taxonomy_version=taxonomy.version if manual_category else None,
                primary_category=manual_category,
                secondary_categories=[],
                classification_status=(
                    classification_status_for(manual_category) if manual_category else "pending"
                ),
                classification_confidence=1.0 if manual_category else None,
                classification_source="manual" if manual_category else None,
                classification_reason="上传时人工指定" if manual_category else None,
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
    section: str | None = None,
    breadth_source: str | None = None,
    primary_category: str | None = None,
    classification_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """按分区过滤；同时返回各分区计数（counts/counts_breadth），供资料库导航展示。"""
    filters = []
    if section:
        if section not in PRIMARY_SECTIONS:
            raise HTTPException(400, "一级分区只能是：breadth / industry / atsc")
        filters.append(UploadedFile.primary_section == section)
        # 广度二级：请求具体来源时精确过滤；未指明来源时返回该一级分区全部
        if breadth_source:
            if breadth_source not in BREADTH_SOURCES:
                raise HTTPException(400, "广度来源只能是：github / other")
            filters.append(UploadedFile.breadth_source == breadth_source)
    if primary_category:
        filters.append(UploadedFile.primary_category == primary_category)
    if classification_status:
        filters.append(UploadedFile.classification_status == classification_status)

    query = select(UploadedFile).where(*filters).order_by(UploadedFile.created_at.desc())
    count_query = select(func.count()).select_from(UploadedFile).where(*filters)
    rows = db.scalars(query.limit(max(1, min(limit, 500))).offset(max(0, offset))).all()
    # 各分区计数（不受当前过滤影响，供导航角标/计数展示）
    section_counts = dict(
        db.execute(
            select(UploadedFile.primary_section, func.count()).group_by(UploadedFile.primary_section)
        ).all()
    )
    breadth_counts = dict(
        db.execute(
            select(UploadedFile.breadth_source, func.count())
            .where(UploadedFile.primary_section == "breadth")
            .group_by(UploadedFile.breadth_source)
        ).all()
    )
    return {
        "count": db.scalar(count_query) or 0,
        "files": [_serialize(row) for row in rows],
        "counts": {
            "breadth": section_counts.get("breadth", 0),
            "industry": section_counts.get("industry", 0),
            "atsc": section_counts.get("atsc", 0),
            "github": breadth_counts.get("github", 0),
            "other": breadth_counts.get("other", 0),
        },
    }


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
    # 增量包/逐行表格导入：索引走持久队列，重试 = 失败任务重新入队；
    # 旧导入（队列启用前，状态 skipped 且从无任务）首次补建全部行的任务
    has_tasks = db.scalar(select(IndexTask.id).where(IndexTask.upload_id == record.id)) is not None
    is_zip_import = record.primary_section == "breadth" and record.breadth_source == "github"
    if has_tasks or (is_zip_import and record.embedding_status in {"queued", "skipped"}):
        from app.models.breadth_manual_record import BreadthManualRecord
        from app.services.breadth_index_queue import enqueue_record_upserts, process_batch

        tasks = db.scalars(select(IndexTask).where(IndexTask.upload_id == record.id)).all()
        rows = db.scalars(
            select(BreadthManualRecord).where(BreadthManualRecord.upload_id == record.id)
        ).all()
        if rows and not tasks:
            enqueue_record_upserts(db, rows)
        else:
            for task in tasks:
                if task.status in ("failed", "pending"):
                    task.status = "pending"
                    task.attempts = 0
                    task.not_before = None
                    task.last_error = None
        record.embedding_status = "queued"
        record.embedding_error = None
        db.commit()
        background_tasks.add_task(process_batch)
        return {"id": str(record.id), "embedding_status": "queued"}
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
    # 其他广度情报：人工改分类同步到广度总表记录
    from app.models.breadth_manual_record import BreadthManualRecord
    breadth_record = db.scalar(
        select(BreadthManualRecord).where(BreadthManualRecord.upload_id == record.id)
    )
    if breadth_record is not None:
        breadth_record.category = primary
        breadth_record.document_date = record.document_date
        db.commit()
    background_tasks.add_task(process_uploaded_file, str(record.id))
    return _serialize(record)


class RenamePayload(BaseModel):
    title: str = Field(min_length=1, max_length=500)


@router.patch("/uploads/{file_id}/title")
def rename_upload(
    file_id: str,
    payload: RenamePayload,
    current_user: str = Depends(require_upload),
    db: Session = Depends(get_db),
) -> dict:
    """重命名资料标题：admin 与 ATSC 可改名任意资料；普通用户 403（require_upload）。"""
    record = db.get(UploadedFile, _uuid_or_400(file_id))
    if record is None:
        raise HTTPException(404, "资料不存在")
    try:
        return rename_uploaded_file(db, record, payload.title)
    except UploadValidationError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/uploads/{file_id}/download")
def download_upload(
    file_id: str,
    current_user: str = Depends(require_upload),
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
    # v7（0023）：size_bytes 业务字段已移除，Content-Length 以实际文件为准
    content_length = path.stat().st_size
    return StreamingResponse(
        iterfile(),
        media_type=record.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_name}",
            "Content-Length": str(content_length),
        },
    )

@router.delete("/uploads/{file_id}")
def delete_upload(
    file_id: str,
    current_user: str = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    # 删除一条已上传资料：问答索引 -> 落盘文件 -> 数据库记录，三处同步删除。
    _uuid_or_400(file_id)
    record = db.get(UploadedFile, uuid.UUID(file_id))
    if record is None:
        raise HTTPException(404, "资料不存在")
    # 防竞态：分类/索引处理进行中时不允许删除，否则后台任务可能在记录删除后
    # 仍把内容写入问答索引，造成"已删除却可检索"。
    if record.classification_status == "processing" or record.embedding_status == "processing":
        raise HTTPException(409, "资料正在分类或建立索引，请稍后再删除")
    try:
        result = delete_uploaded_file(db, record)
    except (RuntimeError, httpx.TransportError) as exc:
        # 网络层失败与 RuntimeError 同类处理：保证“记录已删但问答仍可检索”不出现
        raise HTTPException(502, "问答索引删除失败，资料未被删除：" + str(exc)) from exc
    return result



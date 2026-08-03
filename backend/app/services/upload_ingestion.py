from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import UploadFile
from sqlalchemy import select, update

from app.core.classification import (
    AI_CONFIDENTIALITY_LEVELS,
    CONFIDENTIALITY_LEVELS,
    normalize_confidentiality,
)
from app.db.session import SessionLocal
from app.models.uploaded_file import UploadedFile


logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_BATCH_FILES = 20
MAX_BATCH_BYTES = 200 * 1024 * 1024
STREAM_CHUNK_BYTES = 1024 * 1024
MAX_CLASSIFICATION_TEXT_CHARS = 12_000

ALLOWED_EXTS: dict[str, bool] = {
    ".pdf": True,
    ".docx": True,
    ".xlsx": True,
    ".md": True,
    ".markdown": True,
    ".txt": True,
    ".csv": True,
    ".png": False,
    ".jpg": False,
    ".jpeg": False,
}

SOURCE_TYPES = {"论文", "专利", "研报", "网页快照", "同事材料", "付费数据库", "其他"}
RESULT_LABELS = {"未分类", "不相关"}


class UploadValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class StoredUpload:
    stored_filename: str
    path: Path
    size_bytes: int
    checksum_sha256: str


@dataclass(frozen=True)
class Taxonomy:
    taxonomy_id: str
    version: str
    categories: tuple[str, ...]
    business_categories: tuple[str, ...]
    result_labels: tuple[str, ...]


def upload_root() -> Path:
    return Path(os.getenv("TECHDB_UPLOAD_DIR", "/app/uploads")).resolve()


def _project_taxonomy_paths() -> tuple[Path, Path]:
    project_root = Path(__file__).resolve().parents[3]
    data_root = Path(os.getenv("BREADTH_DATA_PATH", "/app/breadth_data"))
    if not data_root.exists():
        data_root = project_root / "breadth" / "data"
    return data_root / "category-taxonomy.json", data_root / "taxonomy-manifest.json"


@lru_cache(maxsize=1)
def load_taxonomy() -> Taxonomy:
    taxonomy_path, manifest_path = _project_taxonomy_paths()
    try:
        taxonomy_data = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"分类目录不可用: {exc}") from exc

    categories = tuple(str(item).strip() for item in taxonomy_data.get("categories", []) if str(item).strip())
    result_labels = tuple(str(item).strip() for item in manifest.get("result_labels", []) if str(item).strip())
    if len(categories) != int(manifest.get("output_count", 0)):
        raise RuntimeError("分类目录数量与 manifest 不一致")
    if set(result_labels) != RESULT_LABELS or not RESULT_LABELS.issubset(categories):
        raise RuntimeError("分类目录缺少未分类/不相关处理结果")
    if len(set(categories)) != len(categories):
        raise RuntimeError("分类目录存在重复路径")

    business_categories = tuple(item for item in categories if item not in RESULT_LABELS)
    if len(business_categories) != int(manifest.get("business_category_count", 0)):
        raise RuntimeError("业务分类数量与 manifest 不一致")

    return Taxonomy(
        taxonomy_id=str(manifest["taxonomy_id"]),
        version=str(manifest["taxonomy_version"]),
        categories=categories,
        business_categories=business_categories,
        result_labels=result_labels,
    )


def file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_filename(filename: str) -> str:
    ext = file_extension(filename)
    if ext not in ALLOWED_EXTS:
        allowed = ", ".join(ALLOWED_EXTS)
        raise UploadValidationError(f"不支持的文件类型：{filename}（仅支持 {allowed}）")
    return ext


def safe_upload_path(stored_filename: str) -> Path:
    root = upload_root()
    candidate = (root / stored_filename).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("非法存储键")
    return candidate


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


async def persist_upload(upload: UploadFile) -> StoredUpload:
    filename = upload.filename or "unnamed"
    ext = validate_filename(filename)
    root = upload_root()
    incoming = root / ".incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    object_id = uuid.uuid4().hex
    target_dir = root / "objects" / object_id[:2]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{object_id}{ext}"
    temp = incoming / f"{object_id}.part"

    digest = hashlib.sha256()
    size = 0
    try:
        with open(temp, "xb") as handle:
            while chunk := await upload.read(STREAM_CHUNK_BYTES):
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise UploadValidationError(
                        f"文件过大（>{MAX_FILE_BYTES // 1024 // 1024}MB）：{filename}",
                        status_code=413,
                    )
                digest.update(chunk)
                handle.write(chunk)
            if size == 0:
                raise UploadValidationError(f"文件为空：{filename}")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp, target)
        _fsync_directory(target_dir)
    except Exception:
        temp.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return StoredUpload(
        stored_filename=target.relative_to(root).as_posix(),
        path=target,
        size_bytes=size,
        checksum_sha256=digest.hexdigest(),
    )


def remove_stored_upload(stored: StoredUpload) -> None:
    stored.path.unlink(missing_ok=True)


def classification_status_for(category: str) -> str:
    if category == "未分类":
        return "unclassified"
    if category == "不相关":
        return "irrelevant"
    return "classified"


def _append_limited(parts: list[str], text: str) -> bool:
    if not text:
        return False
    current = sum(len(item) for item in parts)
    if current >= MAX_CLASSIFICATION_TEXT_CHARS:
        return True
    parts.append(text[: MAX_CLASSIFICATION_TEXT_CHARS - current])
    return sum(len(item) for item in parts) >= MAX_CLASSIFICATION_TEXT_CHARS


def extract_text(path: Path, original_filename: str) -> str | None:
    ext = file_extension(original_filename)
    try:
        if ext in (".md", ".markdown", ".txt", ".csv"):
            with open(path, "rb") as handle:
                raw = handle.read(MAX_CLASSIFICATION_TEXT_CHARS * 4)
            return raw.decode("utf-8", errors="replace")[:MAX_CLASSIFICATION_TEXT_CHARS].strip() or None

        parts: list[str] = []
        if ext == ".pdf":
            from pypdf import PdfReader

            for page in PdfReader(str(path)).pages:
                if _append_limited(parts, page.extract_text() or ""):
                    break
        elif ext == ".docx":
            from docx import Document

            for paragraph in Document(str(path)).paragraphs:
                if _append_limited(parts, paragraph.text):
                    break
        elif ext == ".xlsx":
            from openpyxl import load_workbook

            workbook = load_workbook(str(path), read_only=True, data_only=True)
            try:
                stop = False
                for worksheet in workbook.worksheets:
                    for row in worksheet.iter_rows(values_only=True):
                        text = "\t".join(str(cell) for cell in row if cell is not None)
                        if _append_limited(parts, text):
                            stop = True
                            break
                    if stop:
                        break
            finally:
                workbook.close()
        else:
            return None
        return "\n".join(parts).strip() or None
    except Exception as exc:
        logger.warning("text extraction failed for %s: %s", original_filename, exc)
        return None


def _parse_json_response(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("AI 返回值不是 JSON 对象")
    return parsed


def request_ai_classification(text: str, taxonomy: Taxonomy) -> dict:
    api_key = os.getenv("TECHDB_AGENT_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TECHDB_AGENT_API_KEY 未配置")
    base_url = os.getenv("TECHDB_AGENT_BASE_URL", "https://aigate.catl.com/v1").rstrip("/")
    model = os.getenv("TECHDB_AGENT_MODEL", "GLM-5.2")
    timeout = int(os.getenv("TECHDB_AGENT_AI_TIMEOUT_SECONDS", "90"))

    category_json = json.dumps(taxonomy.categories, ensure_ascii=False)
    prompt = (
        "你是技术资料元数据与分类器。直接输出 JSON，不要解释。\n"
        "primary_category 必须精确取自候选目录；最多给出 3 个 secondary_categories，"
        "且不得包含未分类或不相关。证据不足时 primary_category 选未分类；"
        "内容不属于目录覆盖范围时选不相关。\n"
        "JSON 格式："
        '{"title":"不超过60字的中文标题","confidentiality":"公开|内部",'
        '"source_type":"论文|专利|研报|网页快照|同事材料|付费数据库|其他",'
        '"primary_category":"候选目录中的精确值","secondary_categories":[],"confidence":0.0,"reason":"简短依据"}\n'
        f"分类目录版本：{taxonomy.version}\n候选目录：{category_json}\n\n"
        f"资料文本：\n{text[:MAX_CLASSIFICATION_TEXT_CHARS]}"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 1600,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    result = _parse_json_response(data["choices"][0]["message"]["content"])

    primary = str(result.get("primary_category") or "").strip()
    if primary not in taxonomy.categories:
        raise ValueError("AI 返回了目录之外的主分类")
    secondary: list[str] = []
    for item in result.get("secondary_categories") or []:
        value = str(item).strip()
        if value in taxonomy.business_categories and value != primary and value not in secondary:
            secondary.append(value)
        if len(secondary) == 3:
            break

    confidence = result.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = None

    try:
        ai_confidentiality = normalize_confidentiality(result.get("confidentiality"))
    except ValueError:
        ai_confidentiality = None
    if ai_confidentiality not in AI_CONFIDENTIALITY_LEVELS:
        ai_confidentiality = None

    return {
        "title": str(result.get("title") or "").strip()[:500] or None,
        "confidentiality": ai_confidentiality,
        "source_type": str(result.get("source_type") or "").strip(),
        "primary_category": primary,
        "secondary_categories": secondary,
        "confidence": confidence,
        "reason": str(result.get("reason") or "").strip()[:2000] or None,
    }


def _commit_processing_result(db, file_id: uuid.UUID, **values) -> bool:
    updated = db.execute(
        update(UploadedFile)
        .where(
            UploadedFile.id == file_id,
            UploadedFile.classification_status == "processing",
        )
        .values(**values)
    )
    db.commit()
    return updated.rowcount == 1


def classify_uploaded_file(file_id: str | uuid.UUID) -> bool:
    try:
        uid = file_id if isinstance(file_id, uuid.UUID) else uuid.UUID(str(file_id))
    except ValueError:
        return False

    db = SessionLocal()
    try:
        claimed = db.execute(
            update(UploadedFile)
            .where(UploadedFile.id == uid, UploadedFile.classification_status == "pending")
            .values(
                classification_status="processing",
                classification_attempts=UploadedFile.classification_attempts + 1,
                classification_error=None,
            )
        )
        db.commit()
        if claimed.rowcount != 1:
            return False

        record = db.get(UploadedFile, uid)
        if record is None:
            return False
        taxonomy = load_taxonomy()
        path = safe_upload_path(record.stored_filename)
        if not path.is_file():
            _commit_processing_result(
                db,
                uid,
                storage_status="missing",
                classification_status="failed",
                classification_error="落盘文件不存在",
            )
            return False

        text = extract_text(path, record.original_filename)
        if not text:
            return _commit_processing_result(
                db,
                uid,
                taxonomy_version=taxonomy.version,
                primary_category="未分类",
                secondary_categories=[],
                classification_status="unclassified",
                classification_source="system",
                classification_reason="当前文件无法提取可分类文本",
                classification_error=None,
                classified_at=datetime.now(timezone.utc),
            )

        result = request_ai_classification(text, taxonomy)
        db.refresh(record)
        if record.classification_status != "processing":
            return False
        values = {
            "taxonomy_version": taxonomy.version,
            "primary_category": result["primary_category"],
            "secondary_categories": result["secondary_categories"],
            "classification_status": classification_status_for(result["primary_category"]),
            "classification_confidence": result["confidence"],
            "classification_source": "ai",
            "classification_reason": result["reason"],
            "classification_error": None,
            "classified_at": datetime.now(timezone.utc),
        }
        if record.title_source != "manual" and result["title"]:
            values["title"] = result["title"]
            values["title_source"] = "ai_filled"
        if not record.confidentiality and result["confidentiality"] in AI_CONFIDENTIALITY_LEVELS:
            values["confidentiality"] = result["confidentiality"]
        if not record.source_type and result["source_type"] in SOURCE_TYPES:
            values["source_type"] = result["source_type"]
        return _commit_processing_result(db, uid, **values)
    except Exception as exc:
        db.rollback()
        logger.warning("upload classification failed for %s: %s", file_id, exc)
        try:
            _commit_processing_result(
                db,
                uid,
                classification_status="failed",
                classification_error=str(exc)[:2000],
            )
        except Exception:
            db.rollback()
            logger.exception("failed to persist upload classification error for %s", file_id)
        return False
    finally:
        db.close()


def reconcile_upload_storage() -> None:
    db = SessionLocal()
    try:
        records = db.scalars(
            select(UploadedFile).where(UploadedFile.checksum_sha256.is_(None))
        ).all()
        for record in records:
            try:
                path = safe_upload_path(record.stored_filename)
            except ValueError:
                record.storage_status = "invalid_path"
                continue
            if not path.is_file():
                record.storage_status = "missing"
                continue
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                while chunk := handle.read(STREAM_CHUNK_BYTES):
                    digest.update(chunk)
            record.checksum_sha256 = digest.hexdigest()
            record.storage_status = "stored"
        db.commit()
    finally:
        db.close()


def recover_pending_uploads() -> None:
    reconcile_upload_storage()
    db = SessionLocal()
    try:
        db.execute(
            update(UploadedFile)
            .where(UploadedFile.classification_status == "processing")
            .values(classification_status="pending", classification_error="服务重启后自动恢复")
        )
        db.commit()
        pending_ids = db.scalars(
            select(UploadedFile.id).where(UploadedFile.classification_status == "pending")
        ).all()
    finally:
        db.close()
    for file_id in pending_ids:
        classify_uploaded_file(file_id)

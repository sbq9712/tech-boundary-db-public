from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.classification import (
    AI_CONFIDENTIALITY_LEVELS,
    normalize_confidentiality,
)
from app.db.session import SessionLocal
from app.models.uploaded_file import UploadedFile

logger = logging.getLogger(__name__)

STREAM_CHUNK_BYTES = 1024 * 1024
# 分类输入取整篇代表性采样（头/中/尾），而非只截前若干字，避免封面/目录主导模型判断。
CLASSIFICATION_BUDGET_CHARS = 40_000
INDEX_MODEL = "bge-m3"
INDEX_DIM = 1024


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


def validate_filename(filename: str, mime_type: str | None = None) -> str:
    from app.document_ingestion.parser import input_suffix
    try:
        return input_suffix(filename, mime_type)
    except ValueError as exc:
        raise UploadValidationError(str(exc), status_code=415) from exc


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
    ext = validate_filename(filename, upload.content_type)
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


def extract_text(path: Path, original_filename: str, max_chars: int | None = CLASSIFICATION_BUDGET_CHARS) -> str | None:
    """Compatibility API; all conversion is now native Docling (including OCR)."""
    from app.document_ingestion.docling_processor import convert
    text = convert(path).document.export_to_markdown().strip()
    return (text[:max_chars] if max_chars is not None else text) or None


def ensure_extractable(path: Path, original_filename: str) -> None:
    if not extract_text(path, original_filename):
        raise UploadValidationError(f"Docling 未提取出内容：{original_filename}", status_code=422)


def representative_sample(text: str | None, budget: int) -> str:
    """Return up to ``budget`` chars representing the whole document.

    小文档原样返回；长文档按头/中/尾 4:3:3 采样，避免分类被封面、目录、引言主导。
    """
    if not text:
        return ""
    if len(text) <= budget:
        return text
    overhead = 6  # 三处 "\n…\n" 分隔标记
    target = max(1, budget - overhead)
    head = int(target * 0.4)
    tail = int(target * 0.3)
    mid = target - head - tail
    mid_start = (len(text) - mid) // 2
    return f"{text[:head]}\n…\n{text[mid_start:mid_start + mid]}\n…\n{text[-tail:]}"


def _parse_json_response(content: str) -> dict:
    content = (content or "").strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # 模型可能把 JSON 包在散文里或只吐了片段：抠出最外层 {...} 再试一次。
        match = re.search(r"\{.*\}", content, flags=re.S)
        if match is None:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("AI 返回值不是 JSON 对象")
    return parsed


_CATEGORY_STRIP_CHARS = "\"'`·。.、，,；;：:（）()[]【】「」『』 \t\r\n"


def _normalize_category(value: str) -> str:
    """去掉包裹引号/标点和空白后用于比对，避免模型返回 ``"煤化工"`` / ``煤化工。`` 判失败。"""
    cleaned = value.translate(str.maketrans("", "", _CATEGORY_STRIP_CHARS))
    return re.sub(r"\s+", "", cleaned)


def _match_category(value: str, categories: tuple[str, ...]) -> str | None:
    """把模型返回的类目解析到规范分类路径。

    顺序：精确命中 → 归一化命中（去引号/标点/空白）→ 高阈值模糊命中（difflib≥0.9）。
    都不满足返回 None，交由上层判失败。
    """
    if not value:
        return None
    if value in categories:
        return value
    by_normalized = {_normalize_category(category): category for category in categories}
    normalized = _normalize_category(value)
    if normalized in by_normalized:
        return by_normalized[normalized]
    candidates = difflib.get_close_matches(value, list(categories), n=1, cutoff=0.9)
    return candidates[0] if candidates else None


def request_ai_classification(text: str, taxonomy: Taxonomy) -> dict:
    api_key = os.getenv("TECHDB_AGENT_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TECHDB_AGENT_API_KEY 未配置")
    base_url = os.getenv("TECHDB_AGENT_BASE_URL", "https://aigate.catl.com/v1").rstrip("/")
    model = os.getenv("TECHDB_AGENT_MODEL", "GLM-5.2")
    timeout = int(os.getenv("TECHDB_AGENT_AI_TIMEOUT_SECONDS", "180"))
    max_retries = max(0, int(os.getenv("TECHDB_AGENT_MAX_RETRIES", "2")))
    base_delay = float(os.getenv("TECHDB_AGENT_RETRY_BASE_DELAY_SECONDS", "2"))

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
        f"资料文本（可能为整篇代表性采样）：\n{text[:CLASSIFICATION_BUDGET_CHARS]}"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 1600,
    }
    result: dict | None = None
    raw_content: str | None = None
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            raw_content = str(data["choices"][0]["message"]["content"])
            result = _parse_json_response(raw_content)
            break
        except httpx.HTTPStatusError as exc:
            # 仅重试瞬时错误（429/5xx）；其余 4xx 是请求本身问题，重试无意义。
            if exc.response.status_code not in {429, 500, 502, 503, 504}:
                raise
            last_error = exc
        except (httpx.TimeoutException, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
            # 超时、坏 JSON、响应形状异常 —— 都值得再试一次。
            last_error = exc
        if attempt < max_retries:
            time.sleep(base_delay * (2 ** attempt))
    else:
        raise RuntimeError(
            f"分类模型调用失败（重试 {max_retries} 次后仍不可用）：{last_error}"
        ) from last_error
    if result is None:
        raise RuntimeError("分类结果不可用")

    primary_raw = str(result.get("primary_category") or "").strip()
    primary = _match_category(primary_raw, taxonomy.categories)
    if primary is None:
        raise ValueError(
            f"AI 返回了目录之外的主分类：{primary_raw!r}（原始返回：{(raw_content or '')[:300]!r}）"
        )
    secondary: list[str] = []
    for item in result.get("secondary_categories") or []:
        resolved = _match_category(str(item).strip(), taxonomy.business_categories)
        if resolved and resolved != primary and resolved not in secondary:
            secondary.append(resolved)
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


def request_incremental_index(record: UploadedFile, chunks: list[dict]) -> dict:
    """Send Docling semantic chunks without re-chunking or losing provenance."""
    if not chunks:
        return {"chunk_count": 0, "status": "skipped"}
    base_url = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TECHDB_QA_SERVICE_URL 未配置，无法写入增量索引")
    timeout = float(os.getenv("TECHDB_QA_INDEX_TIMEOUT_SECONDS", "300"))
    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    payload = {
        "document_id": str(record.id),
        "filename": record.original_filename,
        "title": record.title or record.original_filename,
        "primary_category": record.primary_category or "未分类",
        "secondary_categories": record.secondary_categories or [],
        "confidentiality": record.confidentiality,
        "source_type": record.source_type,
        "checksum_sha256": record.checksum_sha256,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "chunks": chunks,
    }
    headers = {"X-TechDB-Index-Token": token} if token else {}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}/api/index/upsert", headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
    if result.get("status") != "ready":
        raise RuntimeError("canonical-qa 未确认增量索引已写入")
    return result


def request_incremental_index_delete(document_id: str) -> dict:
    """Remove one uploaded document from the canonical-qa incremental index.

    Returns {"removed_chunks": int, "skipped": bool}. ``skipped`` 只在检索服务
    未配置时为 True（该环境下资料本就未写入问答索引）。
    """
    base_url = os.getenv("TECHDB_QA_SERVICE_URL", "").strip().rstrip("/")
    if not base_url:
        return {"removed_chunks": 0, "skipped": True}
    timeout = float(os.getenv("TECHDB_QA_INDEX_TIMEOUT_SECONDS", "300"))
    token = os.getenv("TECHDB_QA_INDEX_TOKEN", "").strip()
    headers = {"X-TechDB-Index-Token": token} if token else {}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url}/api/index/delete",
            headers=headers,
            json={"document_id": document_id},
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            # 未索引过（或已删除）：幂等成功
            return {"removed_chunks": 0, "skipped": False}
        response.raise_for_status()
        result = response.json()
    if result.get("status") != "ok":
        raise RuntimeError("canonical-qa 未确认增量索引已删除")
    return {"removed_chunks": int(result.get("removed_chunks") or 0), "skipped": False}


def delete_uploaded_file(db: Session, record: UploadedFile) -> dict:
    """Delete one uploaded file everywhere: QA index → disk → database.

    任一步失败即中止并抛出 RuntimeError/UploadValidationError，保证不出现
    "记录已删但问答仍可检索"或"索引已删但记录还在且重试无门"的状态。
    """
    index_result = request_incremental_index_delete(str(record.id))
    try:
        path = safe_upload_path(record.stored_filename)
    except ValueError:
        path = None
    if path is not None and path.is_file():
        path.unlink()
    import shutil

    from app.document_ingestion.storage import document_directory
    derivatives = document_directory(upload_root(), str(record.id))
    if derivatives.exists():
        shutil.rmtree(derivatives)
    db.delete(record)
    db.commit()
    return {
        "ok": True,
        "removed_chunks": index_result.get("removed_chunks", 0),
        "index_skipped": bool(index_result.get("skipped")),
    }


def _commit_embedding_result(db, file_id: uuid.UUID, **values) -> bool:
    updated = db.execute(
        update(UploadedFile)
        .where(UploadedFile.id == file_id, UploadedFile.embedding_status == "processing")
        .values(**values)
    )
    db.commit()
    return updated.rowcount == 1


def process_uploaded_file(file_id: str | uuid.UUID) -> bool:
    """Classify (when needed), embed and publish one uploaded file."""
    try:
        uid = file_id if isinstance(file_id, uuid.UUID) else uuid.UUID(str(file_id))
    except ValueError:
        return False

    db = SessionLocal()
    classification_claimed = False
    try:
        claimed = db.execute(
            update(UploadedFile)
            .where(UploadedFile.id == uid, UploadedFile.embedding_status == "pending")
            .values(
                embedding_status="processing",
                embedding_attempts=UploadedFile.embedding_attempts + 1,
                embedding_error=None,
            )
        )
        db.commit()
        if claimed.rowcount != 1:
            return False

        record = db.get(UploadedFile, uid)
        if record is None:
            return False
        try:
            path = safe_upload_path(record.stored_filename)
        except ValueError:
            path = None
        if path is None or not path.is_file():
            _commit_embedding_result(
                db,
                uid,
                storage_status="missing",
                embedding_status="failed",
                embedding_error="落盘文件不存在",
            )
            return False

        from app.document_ingestion.service import ingest
        assets, text, chunks = ingest(
            root=upload_root(), original=path, document_id=str(uid),
            filename=record.original_filename, checksum=record.checksum_sha256,
            previous=record.document_assets,
        )
        if not _commit_embedding_result(db, uid, document_assets=assets):
            return False
        db.refresh(record)
        if record.classification_status in {"pending", "processing"}:
            taxonomy = load_taxonomy()
            classification_claimed = True
            if record.classification_status == "pending":
                claimed_classification = db.execute(
                    update(UploadedFile)
                    .where(UploadedFile.id == uid, UploadedFile.classification_status == "pending")
                    .values(
                        classification_status="processing",
                        classification_attempts=UploadedFile.classification_attempts + 1,
                        classification_error=None,
                    )
                )
                db.commit()
                if claimed_classification.rowcount != 1:
                    db.refresh(record)
                else:
                    classification_claimed = True
            if not text:
                # Docling 已完成转换；此处仅处理没有可分类文本的结果。
                # 与用户约定一致：提取失败是失败，不再标记"未分类"。
                _commit_processing_result(
                    db,
                    uid,
                    taxonomy_version=taxonomy.version,
                    primary_category="未分类",
                    secondary_categories=[],
                    classification_status="failed",
                    classification_source="system",
                    classification_reason="当前文件无法提取可分类文本",
                    classification_error="无法提取可分类文本（请检查加密、空文档或 OCR/模型配置）",
                    classified_at=datetime.now(timezone.utc),
                )
            else:
                result = request_ai_classification(
                    representative_sample(text, CLASSIFICATION_BUDGET_CHARS), taxonomy
                )
                db.refresh(record)
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
                if not _commit_processing_result(db, uid, **values):
                    return False
            db.refresh(record)

        if not text:
            return _commit_embedding_result(
                db,
                uid,
                embedding_status="failed",
                embedding_model=INDEX_MODEL,
                embedding_dim=INDEX_DIM,
                embedding_error="无法提取可索引文本（请检查加密、空文档或 OCR/模型配置）",
                chunk_count=0,
                embedded_at=datetime.now(timezone.utc),
            )
        if record.primary_category == "不相关":
            return _commit_embedding_result(
                db,
                uid,
                embedding_status="skipped",
                embedding_model=INDEX_MODEL,
                embedding_dim=INDEX_DIM,
                embedding_error="资料被分类为不相关",
                chunk_count=0,
                embedded_at=datetime.now(timezone.utc),
            )

        result = request_incremental_index(record, chunks)
        # 纵深防御：若记录在索引写入期间被删除（正常流程已被 409 守卫阻止），
        # 不把 ready 状态写回不存在的行，并立即从问答索引移除刚写入的内容。
        if db.get(UploadedFile, uid) is None:
            request_incremental_index_delete(str(uid))
            return False
        return _commit_embedding_result(
            db,
            uid,
            embedding_status="ready",
            embedding_model=INDEX_MODEL,
            embedding_dim=INDEX_DIM,
            embedding_error=None,
            chunk_count=int(result.get("chunk_count", 0)),
            embedded_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        db.rollback()
        message = str(exc)[:2000]
        logger.warning("upload ingestion failed for %s: %s", file_id, message)
        try:
            values = {"embedding_status": "failed", "embedding_error": message}
            failed_record = db.get(UploadedFile, uid)
            if classification_claimed or (failed_record and failed_record.classification_status in {"pending", "processing"}):
                values.update({"classification_status": "failed", "classification_error": message})
            db.execute(update(UploadedFile).where(UploadedFile.id == uid).values(**values))
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("failed to persist upload ingestion error for %s", file_id)
        return False
    finally:
        db.close()


def classify_uploaded_file(file_id: str | uuid.UUID) -> bool:
    """Backward-compatible entry point; classification now includes embedding."""
    return process_uploaded_file(file_id)


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
            select(UploadedFile.id).where(
                (UploadedFile.classification_status == "pending")
                | (UploadedFile.embedding_status == "pending")
                | (UploadedFile.embedding_status == "processing")
            )
        ).all()
        db.execute(
            update(UploadedFile)
            .where(UploadedFile.embedding_status == "processing")
            .values(embedding_status="pending", embedding_error="服务重启后自动恢复")
        )
        db.commit()
    finally:
        db.close()
    for file_id in pending_ids:
        process_uploaded_file(file_id)


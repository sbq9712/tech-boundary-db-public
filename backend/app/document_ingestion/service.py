"""Original → Docling → durable semantic assets. No embedding or HTTP policy here."""

import json
import logging
import os
import uuid
from importlib.metadata import version
from pathlib import Path

from .chunker import chunks_for
from .docling_processor import conversion_metadata, convert
from .storage import document_directory, publish_bundle, read_bundle, sha256, write_json

logger = logging.getLogger(__name__)


def ingest(
    *,
    root: Path,
    original: Path,
    document_id: str,
    filename: str,
    checksum: str | None,
    previous: dict | None = None,
) -> tuple[dict, str, list[dict]]:
    actual = sha256(original)
    if checksum and checksum != actual:
        raise ValueError("原始文件 SHA-256 不匹配，拒绝索引")
    fingerprint = {
        "schema": 1,
        "docling": version("docling"),
        "docling_core": version("docling-core"),
        "tokenizer": os.getenv("TECHDB_DOCUMENT_TOKENIZER", "BAAI/bge-m3"),
        "max_tokens": int(os.getenv("TECHDB_DOCUMENT_CHUNK_TOKENS", "512")),
        "formulas": os.getenv("TECHDB_DOCLING_FORMULAS", "false"),
        "backend_options_sha256": sha256(
            Path(os.environ["TECHDB_DOCLING_BACKEND_OPTIONS_FILE"])
        )
        if os.getenv("TECHDB_DOCLING_BACKEND_OPTIONS_FILE")
        else None,
    }
    parent = document_directory(root, document_id)
    if previous and previous.get("bundle"):
        candidate = (root / previous["bundle"]).resolve()
        if candidate.parent == parent.resolve():
            cached = read_bundle(candidate, original, fingerprint)
            if cached:
                logger.info(
                    "Reusing verified Docling assets for document %s", document_id
                )
                return previous, cached[1], cached[2]
    logger.info("Docling conversion starting for document %s", document_id)
    result = convert(original)
    logger.info("Docling conversion finished for document %s; starting semantic chunking", document_id)
    document = result.document
    chunks = chunks_for(document, document_id, filename, actual)
    logger.info("Document %s: chunking finished (%d chunks); exporting assets", document_id, len(chunks))
    if not chunks:
        raise ValueError(
            "Docling 未生成可检索内容：请检查空白、加密文件或 OCR/模型配置"
        )
    from docling_core.types.doc import ImageRefMode

    markdown = document.export_to_markdown(image_mode=ImageRefMode.EMBEDDED)
    observation = conversion_metadata(result)

    def write(stage):
        (stage / "document.md").write_text(markdown, encoding="utf-8")
        document.save_as_json(stage / "document.json", image_mode=ImageRefMode.EMBEDDED)
        (stage / "chunks.jsonl").write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks),
            encoding="utf-8",
        )
        (stage / "chunk_metadata.jsonl").write_text(
            "".join(
                json.dumps(c["metadata"], ensure_ascii=False) + "\n" for c in chunks
            ),
            encoding="utf-8",
        )
        write_json(stage / "conversion.json", observation)
        manifest = {
            "document_id": document_id,
            "source_file": filename,
            "original_sha256": actual,
            "original_file": original.relative_to(root).as_posix(),
            "pipeline": fingerprint,
            "chunks_count": len(chunks),
            "conversion": observation,
            "files": {
                p.name: {"sha256": sha256(p), "size": p.stat().st_size}
                for p in stage.iterdir()
            },
        }
        write_json(stage / "manifest.json", manifest)
        return manifest

    directory, manifest = publish_bundle(parent, uuid.uuid4().hex, write)
    assets = {**manifest, "bundle": directory.relative_to(root).as_posix()}
    logger.info(
        "Docling assets durable for document %s: %d chunks", document_id, len(chunks)
    )
    return assets, markdown, chunks

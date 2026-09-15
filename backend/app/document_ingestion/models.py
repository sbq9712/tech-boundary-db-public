"""Prepare and verify the local Docling models used by upload ingestion."""

from __future__ import annotations

import json
import os
import tempfile
from importlib.metadata import version
from pathlib import Path

MANIFEST_NAME = ".techdb-docling-models.json"
SCHEMA_VERSION = 1


def model_root() -> Path:
    return Path(
        os.getenv("TECHDB_DOCLING_ARTIFACTS_PATH", "/app/document-models/docling")
    ).resolve()


def tokenizer_path(root: Path | None = None) -> Path:
    configured = os.getenv("TECHDB_DOCUMENT_TOKENIZER")
    return Path(configured).resolve() if configured else (root or model_root()) / "bge-m3-tokenizer"


def _inventory(root: Path) -> dict[str, int]:
    return {
        path.relative_to(root).as_posix(): path.stat().st_size
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != MANIFEST_NAME
    }


def _expected(root: Path | None = None) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "docling": version("docling"),
        "docling_core": version("docling-core"),
        "tokenizer": str(tokenizer_path(root)),
        "capabilities": ["layout", "tableformer", "code_formula", "rapidocr:onnxruntime:ch"],
    }


def is_ready(root: Path | None = None) -> bool:
    root = root or model_root()
    marker = root / MANIFEST_NAME
    try:
        saved = json.loads(marker.read_text(encoding="utf-8"))
        inventory = saved.pop("files")
        return saved == _expected(root) and bool(inventory) and inventory == _inventory(root)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _write_marker(root: Path) -> None:
    payload = {**_expected(root), "files": _inventory(root)}
    if not payload["files"]:
        raise RuntimeError("Docling 模型下载完成但目录为空")
    fd, temp_name = tempfile.mkstemp(prefix=".models-", suffix=".json", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, root / MANIFEST_NAME)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _download(root: Path) -> None:
    from docling.utils.model_downloader import download_models
    from transformers import AutoTokenizer

    download_models(
        output_dir=root,
        progress=True,
        with_layout=True,
        with_tableformer=True,
        with_code_formula=True,
        with_picture_classifier=False,
        with_rapidocr=True,
        rapidocr_models=["onnxruntime:ch"],
    )
    tokenizer = AutoTokenizer.from_pretrained(
        os.getenv("TECHDB_DOCUMENT_TOKENIZER_SOURCE", "BAAI/bge-m3")
    )
    tokenizer_dir = tokenizer_path(root)
    tokenizer_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(tokenizer_dir)


def ensure_models(root: Path | None = None) -> bool:
    """Return True after download, False when a verified snapshot was reused."""
    root = root or model_root()
    root.mkdir(parents=True, exist_ok=True)
    if is_ready(root):
        print(f"Docling 模型完整，复用本地文件：{root}", flush=True)
        return False

    print(f"首次准备 Docling 布局、表格、公式和 OCR 模型：{root}", flush=True)
    print("下载期间请保持终端开启；完成后再次启动不会重复下载。", flush=True)
    _download(root)
    _write_marker(root)
    if not is_ready(root):
        raise RuntimeError("Docling 模型完整性检查失败，请重新执行本命令")
    print("Docling 模型准备和完整性检查完成。", flush=True)
    return True


if __name__ == "__main__":
    ensure_models()

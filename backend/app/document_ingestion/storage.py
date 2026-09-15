"""Immutable, checksummed derivative bundles on the existing persistent upload volume."""

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def document_directory(root: Path, document_id: str) -> Path:
    return root / "documents" / str(uuid.UUID(document_id))


def read_bundle(directory: Path, original: Path, fingerprint: dict):
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["pipeline"] != fingerprint or manifest["original_sha256"] != sha256(
            original
        ):
            return None
        for name, info in manifest["files"].items():
            if Path(name).name != name or name in {".", ".."}:
                return None
            path = directory / name
            if (
                path.is_symlink()
                or path.stat().st_size != info["size"]
                or sha256(path) != info["sha256"]
            ):
                return None
        required = {
            "document.md",
            "document.json",
            "chunks.jsonl",
            "chunk_metadata.jsonl",
        }
        if not required.issubset(manifest["files"]):
            return None
        chunks = [
            json.loads(line)
            for line in (directory / "chunks.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        if not chunks or len(chunks) != manifest["chunks_count"]:
            return None
        return manifest, (directory / "document.md").read_text(encoding="utf-8"), chunks
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def publish_bundle(parent: Path, name: str, write):
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".building-", dir=parent))
    try:
        result = write(staging)
        for path in staging.iterdir():
            with path.open("rb+") as stream:
                os.fsync(stream.fileno())
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        target = parent / name
        # Each build has a unique final name. No replacement gap on retries/Windows.
        staging.rename(target)
        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return target, result
    finally:
        if staging.exists():
            shutil.rmtree(staging)

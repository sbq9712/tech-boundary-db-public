"""Use the installed Docling registry, not a second format allowlist/parser."""

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def supported_formats() -> dict:
    from docling.datamodel.base_models import FormatToExtensions, FormatToMimeType

    return {
        "engine": "docling",
        "formats": {
            fmt.value: {
                "extensions": ["." + ext.lower() for ext in extensions],
                "mime_types": FormatToMimeType.get(fmt, []),
            }
            for fmt, extensions in FormatToExtensions.items()
        },
        # Historical alias: conversion still goes through Docling's Markdown backend.
        "aliases": {".markdown": ".md"},
    }


def input_suffix(filename: str, mime_type: str | None = None) -> str:
    if not filename or "/" in filename or "\\" in filename or "\x00" in filename:
        raise ValueError("文件名不能包含路径")
    registry = supported_formats()
    name = filename.lower()
    if name.endswith(".markdown"):
        return ".md"
    extensions = {
        ext for entry in registry["formats"].values() for ext in entry["extensions"]
    }
    for ext in sorted(extensions, key=len, reverse=True):
        if name.endswith(ext):
            return ext
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    # Browser MIME is a hint only. Docling still sniffs/validates the actual content.
    for entry in registry["formats"].values():
        if mime in entry["mime_types"]:
            return entry["extensions"][0]
    raise ValueError(
        f"Docling 不支持此文件类型：{Path(filename).name} ({mime or '未知 MIME'})"
    )

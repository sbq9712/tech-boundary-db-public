"""One native Docling conversion path for digital, scanned and image documents."""

import json
import os
from functools import lru_cache
from pathlib import Path
from threading import RLock

_CONVERSION_LOCK = RLock()  # model instances are shared only within this process


@lru_cache(maxsize=1)
def converter():
    import onnxruntime

    onnxruntime.disable_telemetry_events()
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import (
        DocumentConverter,
        ImageFormatOption,
        PdfFormatOption,
    )

    options = PdfPipelineOptions()
    options.do_ocr = (
        True  # native automatic area/text detection, not force-full-page OCR
    )
    options.ocr_options = RapidOcrOptions(backend="onnxruntime")
    options.do_table_structure = True
    options.generate_picture_images = True
    options.generate_parsed_pages = True
    options.heading_hierarchy_options.enabled = True
    options.do_formula_enrichment = (
        os.getenv("TECHDB_DOCLING_FORMULAS", "true").lower() == "true"
    )
    options.enable_remote_services = False
    artifacts = os.getenv("TECHDB_DOCLING_ARTIFACTS_PATH", "").strip()
    if artifacts:
        options.artifacts_path = Path(artifacts)
    engine = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
        }
    )
    # Administrator-supplied native options (e.g. EBCDIC layout), never upload content.
    config_path = os.getenv("TECHDB_DOCLING_BACKEND_OPTIONS_FILE", "").strip()
    if config_path:
        from pydantic import TypeAdapter

        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError(
                "Docling backend options must be a format-to-options JSON object"
            )
        for name, values in config.items():
            option = engine.format_to_options[InputFormat(name)]
            if not isinstance(values, dict):
                raise TypeError("Docling backend options must be objects")
            values = {
                **values,
                "enable_remote_fetch": False,
                "enable_local_fetch": False,
            }
            annotation = type(option).model_fields["backend_options"].annotation
            option.backend_options = TypeAdapter(annotation).validate_python(values)
    return engine


def convert(path: Path):
    from docling.datamodel.base_models import ConversionStatus

    with _CONVERSION_LOCK:
        result = converter().convert(path, raises_on_error=True)
    if result.status != ConversionStatus.SUCCESS:
        raise ValueError(f"Docling 转换未完整成功：{result.status}; {result.errors}")
    return result


def conversion_metadata(result) -> dict:
    """Record observed OCR cells, never infer OCR success merely from do_ocr=True."""
    observations = []
    for page in result.pages:
        parsed = getattr(page, "parsed_page", None)
        cells = getattr(parsed, "textline_cells", []) if parsed else []
        flags = [getattr(cell, "from_ocr", None) for cell in cells]
        observations.append(
            {
                "page_number": page.page_no,
                "ocr_cells": sum(value is True for value in flags),
                "ocr_observable": any(value is not None for value in flags),
            }
        )
    observable = any(page["ocr_observable"] for page in observations)
    return {
        "input_format": result.input.format.value,
        "ocr_enabled": True,
        "ocr_triggered": any(page["ocr_cells"] for page in observations)
        if observable
        else None,
        "pages": observations,
        "errors": [error.model_dump(mode="json") for error in result.errors],
    }

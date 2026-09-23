"""Deterministic contracts; real Docling objects/chunker, no production embedding/model."""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.document_ingestion import metadata, runner, service, storage


def test_identity_and_all_page_provenance():
    native = {
        "headings": ["Results", "Table"],
        "doc_items": [
            {
                "self_ref": "#/tables/0",
                "prov": [{"page_no": 2, "bbox": {"l": 10}}, {"page_no": 3}],
            }
        ],
    }
    chunk = SimpleNamespace(meta=SimpleNamespace(model_dump=lambda **kw: native))
    doc_id = str(uuid.uuid4())
    first = metadata.chunk_record(chunk, "table text", doc_id, "a.pdf", "a" * 64, 0)
    assert first == metadata.chunk_record(
        chunk, "table text", doc_id, "a.pdf", "a" * 64, 0
    )
    assert first["metadata"]["page_numbers"] == [2, 3]
    assert first["metadata"]["provenance"][0]["doc_ref"] == "#/tables/0"
    assert (
        first["chunk_id"]
        != metadata.chunk_record(chunk, "changed", doc_id, "a.pdf", "a" * 64, 0)[
            "chunk_id"
        ]
    )
    assert first["metadata"]["document_id"] == doc_id


def test_missing_page_is_unknown_not_fabricated():
    chunk = SimpleNamespace(
        meta=SimpleNamespace(model_dump=lambda **kw: {"headings": []})
    )
    result = metadata.chunk_record(
        chunk, "text", str(uuid.uuid4()), "a.docx", "a" * 64, 0
    )
    assert result["metadata"]["page_number"] is None
    assert result["metadata"]["page_numbers"] == []


def test_atomic_bundle_failure_leaves_no_published_assets(tmp_path):
    def fail(stage):
        (stage / "document.md").write_text("incomplete")
        raise ValueError("conversion failed")

    with pytest.raises(ValueError):
        storage.publish_bundle(tmp_path, "bundle", fail)
    assert list(tmp_path.iterdir()) == []


def test_original_integrity_failure_precedes_conversion(tmp_path, monkeypatch):
    original = tmp_path / "a.txt"
    original.write_text("corrupt")
    monkeypatch.setattr(
        service, "convert", lambda _: pytest.fail("must not parse corrupt original")
    )
    with pytest.raises(ValueError, match="SHA-256"):
        service.ingest(
            root=tmp_path,
            original=original,
            document_id=str(uuid.uuid4()),
            filename="a.txt",
            checksum="0" * 64,
        )


def test_bundle_cache_checks_every_file_and_fingerprint(tmp_path):
    original = tmp_path / "original.txt"
    original.write_text("original")
    directory = tmp_path / "bundle"
    directory.mkdir()
    chunks = [{"chunk_id": "1", "text": "hello"}]
    for name, text in {
        "document.md": "hello",
        "document.json": "{}",
        "chunks.jsonl": json.dumps(chunks[0]) + "\n",
        "chunk_metadata.jsonl": "{}\n",
    }.items():
        (directory / name).write_text(text)
    fingerprint = {"schema": 1}
    manifest = {
        "pipeline": fingerprint,
        "original_sha256": storage.sha256(original),
        "chunks_count": 1,
        "files": {
            p.name: {"size": p.stat().st_size, "sha256": storage.sha256(p)}
            for p in directory.iterdir()
        },
    }
    storage.write_json(directory / "manifest.json", manifest)
    assert storage.read_bundle(directory, original, fingerprint)[2] == chunks
    assert storage.read_bundle(directory, original, {"schema": 2}) is None
    (directory / "document.md").write_text("altered")
    assert storage.read_bundle(directory, original, fingerprint) is None


def test_registry_and_mime_cover_native_formats():
    from app.document_ingestion.parser import input_suffix, supported_formats
    from docling.datamodel.base_models import FormatToExtensions

    registry = supported_formats()
    assert set(registry["formats"]) == {fmt.value for fmt in FormatToExtensions}
    for extensions in FormatToExtensions.values():
        for extension in extensions:
            assert input_suffix("file." + extension)
    assert input_suffix("no-extension", "application/pdf") == ".pdf"
    assert input_suffix("README.markdown") == ".md"
    for name in ["../a.pdf", "C:\\a.pdf", "file.exe"]:
        with pytest.raises(ValueError):
            input_suffix(name)


def test_hybrid_heading_token_boundary_and_stability(monkeypatch):
    from app.document_ingestion import chunker
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
    from docling_core.types.doc import DocItemLabel, DoclingDocument

    class FixtureTokenizer(BaseTokenizer):
        """Deterministic tokenizer substitute, NOT a bge-m3 model validation."""

        def count_tokens(self, text):
            return len(text.split())

        def get_max_tokens(self):
            return 64

        def get_tokenizer(self):
            return self.count_tokens

    engine = HybridChunker(tokenizer=FixtureTokenizer(), merge_peers=True)
    monkeypatch.setattr(chunker, "chunker", lambda: engine)
    doc = DoclingDocument(name="synthetic")
    doc.add_heading(text="Evidence", level=1)
    for i in range(20):
        doc.add_text(
            label=DocItemLabel.PARAGRAPH,
            text=f"Observation {i}: " + "synthetic evidence " * 30,
        )
    doc_id = str(uuid.uuid4())
    result = chunker.chunks_for(doc, doc_id, "a.docx", "a" * 64)
    assert len(result) > 1
    assert all(len(c["text"].split()) <= 64 for c in result)
    assert all("Evidence" in c["metadata"]["section_title"] for c in result)
    assert result == chunker.chunks_for(doc, doc_id, "a.docx", "a" * 64)
    assert all(
        f"Observation {i}" in " ".join(c["text"] for c in result) for i in range(20)
    )


def test_vector_bm25_reload_and_delete_preserve_docling_provenance(tmp_path):
    """Real canonical storage/search, deterministic embedding double, not bge-m3."""
    import asyncio
    import importlib.util

    import numpy as np

    module_path = (
        Path(__file__).resolve().parents[2]
        / "services/canonical-qa/qa-backend/incremental_index.py"
    )
    spec = importlib.util.spec_from_file_location(
        "docling_incremental_contract", module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def embed(texts):
        return np.ones((len(texts), 1024), dtype=np.float32)

    doc_id = str(uuid.uuid4())
    chunk = {
        "chunk_id": "stable-chunk",
        "text": "synthetic battery evidence",
        "metadata": {
            "document_id": doc_id,
            "page_number": 2,
            "section_title": "Evidence",
            "provenance": [{"doc_ref": "#/texts/1", "provenance": [{"page_no": 2}]}],
        },
    }
    index = module.IncrementalIndex(tmp_path / "index.pkl", embed)
    arguments = {
        "document_id": doc_id,
        "filename": "a.pdf",
        "title": "Evidence",
        "primary_category": "未分类",
        "secondary_categories": [],
        "confidentiality": "内部",
        "source_type": "其他",
        "checksum_sha256": "a" * 64,
        "created_at": None,
        "chunks": [chunk],
    }
    asyncio.run(index.upsert(**arguments))
    asyncio.run(index.upsert(**arguments))
    restored = module.IncrementalIndex(tmp_path / "index.pkl", embed)
    restored.load()
    assert restored.record_count == 1
    assert (
        restored.vector_search(np.ones(1024), 5)[0]["meta"]["chunk_metadata"]
        == chunk["metadata"]
    )
    assert (
        restored.bm25_search("battery", 5)[0]["meta"]["chunk_metadata"]
        == chunk["metadata"]
    )
    asyncio.run(restored.remove_document(doc_id))
    assert not restored.vector_search(np.ones(1024), 5)
    assert not restored.bm25_search("battery", 5)


def test_ingestion_index_failure_preserves_assets_for_retry(monkeypatch, tmp_path):
    from app.services import upload_ingestion

    original = tmp_path / "a.txt"
    original.write_text("synthetic")
    record = SimpleNamespace(
        id=uuid.uuid4(),
        stored_filename="a.txt",
        original_filename="a.txt",
        checksum_sha256=storage.sha256(original),
        document_assets=None,
        document_date=None,
        classification_status="classified",
        primary_category="未分类",
        embedding_status="pending",
        embedding_error=None,
        chunk_count=0,
        primary_section="industry",
        breadth_source=None,
    )
    updates = []

    class Session:
        def execute(self, statement):
            values = statement.compile().params
            updates.append(values)
            for key, value in values.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            return SimpleNamespace(rowcount=1)

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

        def get(self, *args):
            return record

        def refresh(self, *args):
            pass

    bundle = {"bundle": "documents/test/bundle"}
    chunks = [
        {"chunk_id": "stable", "text": "synthetic", "metadata": {"page_number": 1}}
    ]
    previous = []

    def ingest(**kwargs):
        previous.append(kwargs["previous"])
        return bundle, "synthetic", chunks

    monkeypatch.setattr(upload_ingestion, "SessionLocal", Session)
    monkeypatch.setattr(upload_ingestion, "upload_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "ingest", ingest)

    def failed_index(*args):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(upload_ingestion, "request_incremental_index", failed_index)
    assert upload_ingestion.process_uploaded_file(record.id) is False
    assert record.document_assets == bundle and record.embedding_status == "failed"
    assert record.classification_status == "classified"
    record.embedding_status = "pending"
    monkeypatch.setattr(
        upload_ingestion,
        "request_incremental_index",
        lambda rec, data: {"status": "ready", "chunk_count": len(data)},
    )
    assert upload_ingestion.process_uploaded_file(record.id) is True
    assert previous == [None, bundle]
    assert record.embedding_status == "ready" and record.chunk_count == 1


def test_parse_failure_is_reported_instead_of_pending_classification(
    monkeypatch, tmp_path
):
    from app.services import upload_ingestion

    path = tmp_path / "scan.pdf"
    path.write_bytes(b"synthetic test double")
    record = SimpleNamespace(
        id=uuid.uuid4(),
        stored_filename="scan.pdf",
        original_filename="scan.pdf",
        checksum_sha256=storage.sha256(path),
        document_assets=None,
        classification_status="pending",
    )
    statements = []
    db = SimpleNamespace(
        execute=lambda s: (
            statements.append(s.compile().params) or SimpleNamespace(rowcount=1)
        ),
        commit=lambda: None,
        rollback=lambda: None,
        close=lambda: None,
        get=lambda *args: record,
    )
    monkeypatch.setattr(upload_ingestion, "SessionLocal", lambda: db)
    monkeypatch.setattr(upload_ingestion, "upload_root", lambda: tmp_path)

    def fail(**kwargs):
        raise RuntimeError("OCR model missing")

    monkeypatch.setattr(runner, "ingest", fail)
    assert upload_ingestion.process_uploaded_file(record.id) is False
    assert statements[-1]["classification_status"] == "failed"
    assert statements[-1]["embedding_status"] == "failed"
    assert "OCR model missing" in statements[-1]["embedding_error"]


def test_ingestion_disables_native_telemetry_before_conversion(monkeypatch):
    import importlib
    import os

    import app.document_ingestion as ingestion

    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "0")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "0")
    importlib.reload(ingestion)
    assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"



def test_model_snapshot_downloads_once_and_rejects_partial_state(tmp_path, monkeypatch):
    from app.document_ingestion import models

    calls = []
    monkeypatch.setattr(models, "_expected", lambda root=None: {"schema": 1, "engine": "test"})

    def download(root):
        calls.append(root)
        (root / "layout").mkdir(parents=True, exist_ok=True)
        (root / "layout" / "model.bin").write_bytes(b"synthetic model")

    monkeypatch.setattr(models, "_download", download)
    assert models.ensure_models(tmp_path) is True
    assert models.ensure_models(tmp_path) is False
    assert len(calls) == 1
    (tmp_path / "layout" / "model.bin").write_bytes(b"truncated")
    assert models.is_ready(tmp_path) is False
    assert models.ensure_models(tmp_path) is True
    assert len(calls) == 2


def test_upload_status_exposes_docling_before_classification():
    from app.routers.uploads import _serialize

    record = SimpleNamespace(
        storage_status="stored", embedding_status="processing", document_assets=None,
        classification_status="pending", id=uuid.uuid4(), original_filename="paper.pdf",
        chunk_count=0, stored_filename="objects/a.pdf", title="paper",
        domain_refs=None, note=None, title_source="filename_fallback",
        primary_section="industry", breadth_source=None,
        mime_type="application/pdf", document_date="2026-09-01", checksum_sha256="a" * 64,
        taxonomy_version=None, primary_category=None, secondary_categories=[],
        classification_confidence=None, classification_source=None, classification_reason=None,
        classification_error=None, classification_attempts=0, classified_at=None,
        embedding_model=None, embedding_dim=None, embedding_error=None, embedding_attempts=1,
        embedded_at=None, submitted_by="tester", created_at=None,
    )
    assert _serialize(record)["ingestion_status"] == "document_processing"


def test_local_start_prepares_docling_models_before_starting_api():
    root = Path(__file__).resolve().parents[2]
    script = (root / "start_with_local_ai.sh").read_text(encoding="utf-8")

    build_at = script.index('docker compose --env-file "$ENV_FILE" build')
    models_at = script.index("python -m app.document_ingestion.models")
    start_at = script.index('docker compose --env-file "$ENV_FILE" up -d')

    assert build_at < models_at < start_at
    assert "run --rm --no-deps api" in script


@pytest.mark.parametrize("configured, expected", [(None, False), ("false", False), ("true", True)])
def test_formula_enrichment_is_opt_in_without_disabling_structure(monkeypatch, configured, expected):
    from app.document_ingestion import docling_processor
    from docling.datamodel.base_models import InputFormat

    monkeypatch.delenv("TECHDB_DOCLING_BACKEND_OPTIONS_FILE", raising=False)
    if configured is None:
        monkeypatch.delenv("TECHDB_DOCLING_FORMULAS", raising=False)
    else:
        monkeypatch.setenv("TECHDB_DOCLING_FORMULAS", configured)
    docling_processor.converter.cache_clear()
    try:
        engine = docling_processor.converter()
        for kind in (InputFormat.PDF, InputFormat.IMAGE):
            options = engine.format_to_options[kind].pipeline_options
            assert options.do_formula_enrichment is expected
            assert options.do_ocr and options.do_table_structure
            assert options.generate_picture_images and options.generate_parsed_pages
    finally:
        docling_processor.converter.cache_clear()


def test_irrelevant_uploads_are_indexed_by_default_and_keep_label(monkeypatch, tmp_path):
    """上传资料一律入索引：即使判为不相关也照常建立索引，分类标签仅作元数据。"""
    from app.services import upload_ingestion

    original = tmp_path / "a.pdf"
    original.write_text("synthetic")
    record = SimpleNamespace(
        id=uuid.uuid4(),
        stored_filename="a.pdf",
        original_filename="a.pdf",
        checksum_sha256=storage.sha256(original),
        document_assets=None,
        document_date=None,
        classification_status="irrelevant",
        primary_category="不相关",
        primary_section="industry",
        breadth_source=None,
        embedding_status="pending",
        embedding_error=None,
        chunk_count=0,
    )
    updates = []

    class Session:
        def execute(self, statement):
            values = statement.compile().params
            updates.append(values)
            for key, value in values.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            return SimpleNamespace(rowcount=1)

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

        def get(self, *args):
            return record

        def refresh(self, *args):
            pass

    def ingest(**kwargs):
        return {"bundle": "documents/test/bundle"}, "synthetic", [
            {"chunk_id": "c0", "text": "synthetic", "metadata": {"page_number": 2}}
        ]

    monkeypatch.setattr(upload_ingestion, "SessionLocal", Session)
    monkeypatch.setattr(upload_ingestion, "upload_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "ingest", ingest)
    monkeypatch.setattr(
        upload_ingestion,
        "request_incremental_index",
        lambda rec, data: {"status": "ready", "chunk_count": len(data)},
    )

    # 不相关资料默认照常入索引，且分类标签保持不相关
    assert upload_ingestion.process_uploaded_file(record.id) is True
    assert record.embedding_status == "ready"
    assert record.primary_category == "不相关"
    assert record.classification_status == "irrelevant"
    assert record.chunk_count == 1


def test_document_date_is_stamped_into_indexed_chunks(monkeypatch, tmp_path):
    """上传时填写的资料日期必须进入分块：文本前缀 + chunk 元数据。"""
    from app.services import upload_ingestion

    original = tmp_path / "a.txt"
    original.write_text("synthetic")
    record = SimpleNamespace(
        id=uuid.uuid4(),
        stored_filename="a.txt",
        original_filename="a.txt",
        checksum_sha256=storage.sha256(original),
        document_assets=None,
        document_date="2026-09-18",
        classification_status="classified",
        primary_category="通用技术/催化剂",
        primary_section="industry",
        breadth_source=None,
        embedding_status="pending",
        embedding_error=None,
        chunk_count=0,
    )
    indexed: list[list] = []

    class Session:
        def execute(self, statement):
            return SimpleNamespace(rowcount=1)

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

        def get(self, *args):
            return record

        def refresh(self, *args):
            pass

    chunks = [
        {"chunk_id": "stable", "text": "正文一", "metadata": {"page_number": 1}},
        {"chunk_id": "stable2", "text": "正文二", "metadata": {"page_number": 2}},
    ]
    monkeypatch.setattr(upload_ingestion, "SessionLocal", Session)
    monkeypatch.setattr(upload_ingestion, "upload_root", lambda: tmp_path)
    monkeypatch.setattr(
        runner,
        "ingest",
        lambda **kwargs: ({"bundle": "x"}, "synthetic", chunks),
    )
    monkeypatch.setattr(
        upload_ingestion,
        "request_incremental_index",
        lambda rec, data: indexed.append(data) or {"status": "ready", "chunk_count": len(data)},
    )

    assert upload_ingestion.process_uploaded_file(record.id) is True

    assert len(indexed) == 1
    sent = indexed[0]
    assert all(chunk["text"].startswith("【资料日期：2026-09-18】") for chunk in sent)
    assert all(chunk["metadata"]["document_date"] == "2026-09-18" for chunk in sent)
    assert "正文一" in sent[0]["text"] and "正文二" in sent[1]["text"]

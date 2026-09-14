import asyncio
import hashlib
import io
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

from app.services import upload_ingestion


@pytest.fixture(autouse=True)
def clear_taxonomy_cache():
    upload_ingestion.load_taxonomy.cache_clear()
    yield
    upload_ingestion.load_taxonomy.cache_clear()


def test_taxonomy_manifest_defines_77_outputs():
    taxonomy = upload_ingestion.load_taxonomy()

    assert len(taxonomy.categories) == 77
    assert len(taxonomy.business_categories) == 75
    assert set(taxonomy.result_labels) == {"未分类", "不相关"}
    assert taxonomy.version == "4f8594fbc86ebe15948f06496e916fce120f57c8"


def test_persist_upload_writes_immutable_object_and_checksum(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDB_UPLOAD_DIR", str(tmp_path))
    content = b"durable upload content\n"
    upload = UploadFile(filename="report.txt", file=io.BytesIO(content))

    stored = asyncio.run(upload_ingestion.persist_upload(upload))

    assert stored.stored_filename.startswith("objects/")
    assert stored.path.read_bytes() == content
    assert stored.size_bytes == len(content)
    assert stored.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert not list((tmp_path / ".incoming").glob("*.part"))


def test_safe_upload_path_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("TECHDB_UPLOAD_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="非法存储键"):
        upload_ingestion.safe_upload_path("../outside.txt")


@pytest.mark.parametrize(
    ("category", "expected"),
    [("未分类", "unclassified"), ("不相关", "irrelevant"), ("通用技术/催化剂", "classified")],
)
def test_classification_status_mapping(category, expected):
    assert upload_ingestion.classification_status_for(category) == expected


def test_ai_result_outside_taxonomy_is_rejected(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"primary_category":"不存在的分类","secondary_categories":[]}'
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setenv("TECHDB_AGENT_API_KEY", "test-key")
    monkeypatch.setattr(upload_ingestion.httpx, "Client", FakeClient)

    with pytest.raises(ValueError, match="目录之外"):
        upload_ingestion.request_ai_classification("测试资料", upload_ingestion.load_taxonomy())


def test_ai_confidentiality_never_promotes_to_admin(monkeypatch):
    taxonomy = upload_ingestion.load_taxonomy()
    category = taxonomy.business_categories[0]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": (
                            '{"title":"测试资料","confidentiality":"管理员",'
                            f'"source_type":"其他","primary_category":"{category}",'
                            '"secondary_categories":[],"confidence":0.8,"reason":"测试"}'
                        )
                    }
                }]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setenv("TECHDB_AGENT_API_KEY", "test-key")
    monkeypatch.setattr(upload_ingestion.httpx, "Client", FakeClient)

    result = upload_ingestion.request_ai_classification("测试资料", taxonomy)

    assert result["confidentiality"] is None


def test_chunk_text_is_bounded_and_overlapping():
    text = "".join(str(index % 10) for index in range(5_000))

    chunks = upload_ingestion.chunk_text(text)

    assert len(chunks) == 3
    assert all(0 < len(chunk["text"]) <= upload_ingestion.INDEX_CHUNK_CHARS for chunk in chunks)
    assert chunks[0]["text"][-upload_ingestion.INDEX_CHUNK_OVERLAP :] == chunks[1]["text"][: upload_ingestion.INDEX_CHUNK_OVERLAP]


def test_upload_size_and_batch_caps_are_removed():
    """上传不再限制单文件/单批大小与份数（2026-09 需求）。"""
    assert not hasattr(upload_ingestion, "MAX_FILE_BYTES")
    assert not hasattr(upload_ingestion, "MAX_BATCH_FILES")
    assert not hasattr(upload_ingestion, "MAX_BATCH_BYTES")
    assert not hasattr(upload_ingestion, "MAX_INDEX_TEXT_CHARS")


def test_extract_text_without_budget_returns_full_document(tmp_path):
    """max_chars=None 时整篇提取，不受旧 50 万字符上限约束。"""
    body = "甲" * 500_001
    path = tmp_path / "big.txt"
    path.write_text(body, encoding="utf-8")

    extracted = upload_ingestion.extract_text(path, "big.txt", None)

    assert extracted is not None
    assert len(extracted) == len(body)

    # 默认预算（分类采样）仍然截断
    sampled = upload_ingestion.extract_text(path, "big.txt")
    assert len(sampled) <= upload_ingestion.CLASSIFICATION_BUDGET_CHARS


def test_ensure_extractable_rejects_textless_file(tmp_path):
    """上传时同步拒绝无法提取文本的文件，并给出原因。"""
    path = tmp_path / "empty.md"
    path.write_text("   \n\n  ", encoding="utf-8")

    with pytest.raises(upload_ingestion.UploadValidationError) as excinfo:
        upload_ingestion.ensure_extractable(path, "empty.md")
    assert excinfo.value.status_code == 422
    assert "empty.md" in str(excinfo.value)

    # 可以提取文本的文件不应抛错
    ok = tmp_path / "ok.md"
    ok.write_text("# 正常资料\n有内容。", encoding="utf-8")
    upload_ingestion.ensure_extractable(ok, "ok.md")


def test_chunk_text_terminates_on_adversarial_newlines():
    """每行恰好在切分窗口尾部出现换行时也必须推进并终止（回归 codex P0-4 争议项）。"""
    text = ("\n".join("甲" * 1999 for _ in range(200)),)
    text = text[0]

    chunks = upload_ingestion.chunk_text(text)

    assert chunks, "必须产出分块"
    total = sum(len(chunk["text"]) for chunk in chunks)
    # 无限循环不会返回；若返回，说明每轮 start 至少前进 INDEX_CHUNK_CHARS//2 - OVERLAP
    assert total >= len(text) - upload_ingestion.INDEX_CHUNK_OVERLAP


def test_chunk_text_handles_single_giant_line():
    """整篇无换行（10000 字符单行）时按硬边界切分且终止。"""
    text = "乙" * 10_000

    chunks = upload_ingestion.chunk_text(text)

    assert all(0 < len(chunk["text"]) <= upload_ingestion.INDEX_CHUNK_CHARS for chunk in chunks)
    assert len(chunks) >= 5


def test_chunk_text_does_not_skip_text_at_line_boundary():
    text = "A" * 1_500 + "\n" + "B" * 1_500

    chunks = upload_ingestion.chunk_text(text)

    overlap = upload_ingestion.INDEX_CHUNK_OVERLAP
    reconstructed = chunks[0]["text"] + "".join(chunk["text"][overlap:] for chunk in chunks[1:])
    assert reconstructed == text


def test_incremental_index_request_contains_durable_metadata(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "ready", "chunk_count": 1}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs["timeout"]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    file_id = uuid.uuid4()
    record = SimpleNamespace(
        id=file_id,
        original_filename="report.txt",
        title="测试资料",
        primary_category="通用技术/催化剂",
        secondary_categories=["通用技术/材料"],
        confidentiality="内部",
        source_type="研报",
        checksum_sha256="a" * 64,
        created_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://canonical-qa:8765")
    monkeypatch.setenv("TECHDB_QA_INDEX_TOKEN", "test-token")
    monkeypatch.setattr(upload_ingestion.httpx, "Client", FakeClient)

    result = upload_ingestion.request_incremental_index(record, "可索引文本")

    assert result["chunk_count"] == 1
    assert captured["url"] == "http://canonical-qa:8765/api/index/upsert"
    assert captured["headers"] == {"X-TechDB-Index-Token": "test-token"}
    assert captured["json"]["document_id"] == str(file_id)
    assert captured["json"]["primary_category"] == "通用技术/催化剂"
    assert captured["json"]["checksum_sha256"] == "a" * 64
    assert captured["json"]["chunks"] == [{"chunk_id": "0", "text": "可索引文本"}]


def test_representative_sample_returns_small_whole():
    assert upload_ingestion.representative_sample(None, 100) == ""
    assert upload_ingestion.representative_sample("短文本", 100) == "短文本"


def test_representative_sample_covers_head_middle_tail():
    big = "H" * 50000 + "M" * 50000 + "T" * 50000
    sample = upload_ingestion.representative_sample(big, 40000)

    assert len(sample) <= 40000
    assert "H" in sample and "M" in sample and "T" in sample
    assert "…" in sample  # 头/中/尾分隔标记


def test_parse_json_response_recovers_from_prose_and_fences():
    assert upload_ingestion._parse_json_response('{"a": 1}') == {"a": 1}
    assert upload_ingestion._parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert upload_ingestion._parse_json_response('结果如下：{"a": 1} 完成') == {"a": 1}
    with pytest.raises(ValueError):
        upload_ingestion._parse_json_response("[1, 2, 3]")


def test_match_category_accepts_exact_normalized_and_fuzzy():
    taxonomy = upload_ingestion.load_taxonomy()
    target = taxonomy.business_categories[0]
    assert upload_ingestion._match_category(target, taxonomy.categories) == target
    assert upload_ingestion._match_category(f'"{target}"', taxonomy.categories) == target
    assert upload_ingestion._match_category(target + "。", taxonomy.categories) == target
    # 长路径上单字符 typo 的比率 >= 0.9，应模糊命中
    typo = target[:-1] + ("X" if target[-1] != "X" else "Y")
    assert upload_ingestion._match_category(typo, taxonomy.categories) == target
    assert upload_ingestion._match_category("一个根本不存在的分类", taxonomy.categories) is None


def test_classification_retries_on_transient_then_succeeds(monkeypatch):
    taxonomy = upload_ingestion.load_taxonomy()
    category = taxonomy.business_categories[0]
    calls = {"n": 0}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": f'{{"primary_category":"{category}","secondary_categories":[]}}'}}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise upload_ingestion.httpx.TimeoutException("timeout")
            return FakeResponse()

    monkeypatch.setenv("TECHDB_AGENT_API_KEY", "test-key")
    monkeypatch.setenv("TECHDB_AGENT_MAX_RETRIES", "2")
    monkeypatch.setattr(upload_ingestion.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(upload_ingestion.httpx, "Client", FakeClient)

    result = upload_ingestion.request_ai_classification("资料文本", taxonomy)
    assert result["primary_category"] == category
    assert calls["n"] == 2


def test_classification_does_not_retry_on_client_error(monkeypatch):
    taxonomy = upload_ingestion.load_taxonomy()
    calls = {"n": 0}

    class FakeResponse:
        status_code = 400

        def raise_for_status(self):
            raise upload_ingestion.httpx.HTTPStatusError(
                "bad request", request=None, response=self
            )

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, *_args, **_kwargs):
            calls["n"] += 1
            return FakeResponse()

    monkeypatch.setenv("TECHDB_AGENT_API_KEY", "test-key")
    monkeypatch.setenv("TECHDB_AGENT_MAX_RETRIES", "2")
    monkeypatch.setattr(upload_ingestion.time, "sleep", lambda *_a: None)
    monkeypatch.setattr(upload_ingestion.httpx, "Client", FakeClient)

    with pytest.raises(upload_ingestion.httpx.HTTPStatusError):
        upload_ingestion.request_ai_classification("资料文本", taxonomy)
    assert calls["n"] == 1

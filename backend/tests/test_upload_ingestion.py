import asyncio
import hashlib
import io

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

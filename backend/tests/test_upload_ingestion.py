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


def test_normalize_document_date_accepts_common_formats():
    normalize = upload_ingestion.normalize_document_date

    assert normalize(None) is None
    assert normalize("   ") is None
    assert normalize("2026-09-18") == "2026-09-18"
    assert normalize("2026/9/18") == "2026-09-18"
    assert normalize("2026.09.18") == "2026-09-18"
    assert normalize("2026年9月18日") == "2026-09-18"
    assert normalize("2026-09-18T14:30") == "2026-09-18 14:30"
    assert normalize("2026-09-18 14:30:52") == "2026-09-18 14:30"
    assert normalize("2026/09/18 9:05") == "2026-09-18 09:05"
    assert normalize("2026.9.18 08:00") == "2026-09-18 08:00"
    assert normalize("2026年9月18日 14:30") == "2026-09-18 14:30"

    for bad in ("不是日期", "2026-13-01", "2026-09-18 25:00", "1899-12-31", "2026-09/18"):
        with pytest.raises(ValueError):
            normalize(bad)


def test_apply_document_date_stamps_every_chunk():
    chunks = [
        {"chunk_id": "c1", "text": "第一段正文", "metadata": {"page_number": 1}},
        {"chunk_id": "c2", "text": "第二段正文"},
    ]

    upload_ingestion.apply_document_date(chunks, "2026-09-18 14:30")

    assert chunks[0]["text"].startswith("【资料日期：2026-09-18 14:30】")
    assert "第一段正文" in chunks[0]["text"]
    assert chunks[0]["metadata"]["document_date"] == "2026-09-18 14:30"
    assert chunks[1]["text"].startswith("【资料日期：2026-09-18 14:30】")

    # 空日期：原样返回，不改动
    untouched = [{"chunk_id": "c3", "text": "正文", "metadata": {}}]
    upload_ingestion.apply_document_date(untouched, None)
    assert untouched[0]["text"] == "正文"


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


def test_ai_unclassified_output_is_coerced_to_irrelevant(monkeypatch):
    """语义约定：未分类只表示尚未分类；AI 仍输出未分类时按不相关落地。"""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"primary_category":"未分类","secondary_categories":[],'
                                '"confidence":0.3,"reason":"证据不足"}'
                            )
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

    result = upload_ingestion.request_ai_classification(
        "测试资料", upload_ingestion.load_taxonomy()
    )

    assert result["primary_category"] == "不相关"
    assert "证据不足" in (result["reason"] or "")
    assert "按不相关处理" in (result["reason"] or "")


def test_manual_classification_rejects_unclassified():
    from fastapi import HTTPException

    from app.routers.uploads import _validate_category

    with pytest.raises(HTTPException) as exc_info:
        _validate_category("未分类")
    assert exc_info.value.status_code == 400

    # 具体分类与不相关仍然可用
    primary, _ = _validate_category("不相关")
    assert primary == "不相关"


def test_manual_classification_accepts_non_leaf_node():
    from fastapi import HTTPException

    from app.routers.uploads import _validate_category
    from app.services.upload_ingestion import taxonomy_tree_paths

    taxonomy = upload_ingestion.load_taxonomy()
    paths = taxonomy_tree_paths(taxonomy)
    # 全树路径：含叶子、含中间节点、含根，且按层级有序
    assert "零碳产业" in paths
    assert "零碳产业/物质循环" in paths
    assert "零碳产业/物质循环/资源处理/勘探技术" in paths
    assert "不相关" not in paths and "未分类" not in paths

    # 非叶子节点可以人工指定
    primary, _ = _validate_category("零碳产业/物质循环")
    assert primary == "零碳产业/物质循环"

    # 树上不存在的节点拒绝
    with pytest.raises(HTTPException) as exc_info:
        _validate_category("零碳产业/不存在的分支")
    assert exc_info.value.status_code == 400


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

    chunks = [{"chunk_id": "stable-1", "text": "可索引文本", "metadata": {"page_number": 3}}]
    result = upload_ingestion.request_incremental_index(record, chunks)

    assert result["chunk_count"] == 1
    assert captured["url"] == "http://canonical-qa:8765/api/index/upsert"
    assert captured["headers"] == {"X-TechDB-Index-Token": "test-token"}
    assert captured["json"]["document_id"] == str(file_id)
    assert captured["json"]["primary_category"] == "通用技术/催化剂"
    assert captured["json"]["checksum_sha256"] == "a" * 64
    assert captured["json"]["chunks"] == chunks


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

def test_request_incremental_index_delete_posts_document_id(monkeypatch):
    """删除请求携带 document_id 与令牌，返回移除的块数。"""
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "ok", "removed_chunks": 3}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setenv("TECHDB_QA_SERVICE_URL", "http://canonical-qa:8765")
    monkeypatch.setenv("TECHDB_QA_INDEX_TOKEN", "del-token")
    monkeypatch.setattr(upload_ingestion.httpx, "Client", FakeClient)

    result = upload_ingestion.request_incremental_index_delete("doc-1")

    assert result == {"removed_chunks": 3, "skipped": False}
    assert captured["url"] == "http://canonical-qa:8765/api/index/delete"
    assert captured["headers"] == {"X-TechDB-Index-Token": "del-token"}
    assert captured["json"] == {"document_id": "doc-1"}


def test_request_incremental_index_delete_skips_when_unconfigured(monkeypatch):
    """未配置检索服务时跳过索引删除（该环境本就未入索引），不阻断本地删除。"""
    monkeypatch.delenv("TECHDB_QA_SERVICE_URL", raising=False)

    result = upload_ingestion.request_incremental_index_delete("doc-2")

    assert result == {"removed_chunks": 0, "skipped": True}


def test_delete_uploaded_file_removes_index_disk_and_record(tmp_path, monkeypatch):
    """删除编排：先删问答索引，再删落盘文件，最后删数据库记录。"""
    calls = []
    monkeypatch.setattr(
        upload_ingestion,
        "request_incremental_index_delete",
        lambda document_id: calls.append(document_id) or {"removed_chunks": 2, "skipped": False},
    )

    stored_dir = tmp_path / "ab"
    stored_dir.mkdir(parents=True)
    stored = stored_dir / "abc.txt"
    stored.write_text("内容", encoding="utf-8")
    monkeypatch.setattr(upload_ingestion, "upload_root", lambda: tmp_path)

    db = SimpleNamespace(
        delete=lambda record: calls.append("db-delete"),
        commit=lambda: calls.append("db-commit"),
    )
    file_id = uuid.uuid4()
    record = SimpleNamespace(
        id=file_id,
        stored_filename="ab/abc.txt",
    )
    monkeypatch.setattr(
        upload_ingestion,
        "safe_upload_path",
        lambda name: tmp_path / name,
    )

    result = upload_ingestion.delete_uploaded_file(db, record)

    assert result == {"ok": True, "removed_chunks": 2, "index_skipped": False}
    assert calls[0] == str(file_id), "必须先删除问答索引"
    assert "db-delete" in calls and "db-commit" in calls
    assert not stored.exists(), "落盘文件必须被删除"


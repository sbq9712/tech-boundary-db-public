"""Model discovery tests use synthetic credentials and HTTP test doubles only."""
import httpx
import pytest

from app.services import model_catalog


@pytest.fixture(autouse=True)
def clear_cache():
    model_catalog._cache.clear()


def install(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(model_catalog.httpx, "Client", lambda **kw: client(
        transport=httpx.MockTransport(handler), **kw))


def test_discovery_replaces_legacy_models(monkeypatch):
    install(monkeypatch, lambda request: httpx.Response(200, json={"data": [
        {"id": "personal-a"}, {"id": "personal-b"}, {"id": "personal-a"}]}))
    result = model_catalog.get_catalog("https://example.test/v1", "synthetic-key", "company-old", ["company-old"])
    assert result["models"] == ["personal-a", "personal-b"]
    assert result["default_model"] == "personal-a"
    assert result["source"] == "discovered"


def test_cache_is_scoped_to_url_and_key(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [{"id": "model-" + str(len(requests))}]})

    install(monkeypatch, handler)
    get = model_catalog.get_catalog
    assert get("https://one.test/v1", "key-a", "", [])["models"] == ["model-1"]
    assert get("https://one.test/v1", "key-a", "", [])["models"] == ["model-1"]
    assert get("https://one.test/v1", "key-b", "", [])["models"] == ["model-2"]
    assert get("https://two.test/v1", "key-b", "", [])["models"] == ["model-3"]
    assert str(requests[0].url) == "https://one.test/v1/models"
    assert requests[0].headers["Authorization"] == "Bearer key-a"


@pytest.mark.parametrize("status", [404, 405, 501])
def test_unsupported_directory_uses_only_explicit_config(monkeypatch, status):
    install(monkeypatch, lambda request: httpx.Response(status))
    result = model_catalog.get_catalog("https://internal.test/v1", "test-key", "internal-a", ["internal-b"])
    assert result["models"] == ["internal-b", "internal-a"]
    assert result["default_model"] == "internal-a"
    assert result["source"] == "configured"
    assert model_catalog.get_catalog("https://other.test/v1", "test-key", "", [])["models"] == []


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_errors_do_not_fall_back_or_expose_response(monkeypatch, status):
    install(monkeypatch, lambda request: httpx.Response(status, text="secret-upstream-body"))
    result = model_catalog.get_catalog("https://example.test/v1", "private-key", "old-model", ["old-model"])
    assert result["models"] == []
    assert "secret-upstream-body" not in str(result)
    assert "private-key" not in str(result)


@pytest.mark.parametrize("body", [b"not json", b'{"models": []}', b"x" * (1024 * 1024 + 1)])
def test_invalid_or_oversize_catalog_fails_closed(monkeypatch, body):
    install(monkeypatch, lambda request: httpx.Response(200, content=body))
    assert model_catalog.get_catalog("https://example.test", "test-key", "old", [])["models"] == []


def test_timeout_does_not_show_old_models(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("private response")
    install(monkeypatch, handler)
    assert model_catalog.get_catalog("https://example.test", "test-key", "old", [])["models"] == []


@pytest.mark.parametrize("url,key", [("", "key"), ("https://example.test", ""), ("https://[", "key"), ("https://user:pass@example.test", "key")])
def test_invalid_config_never_connects(monkeypatch, url, key):
    def handler(request):
        pytest.fail("invalid configuration must not make a request")
    install(monkeypatch, handler)
    assert model_catalog.get_catalog(url, key, "old", [])["models"] == []

from app.services.hermes_bridge import HermesAgentBridge


def test_bridge_cli_default(monkeypatch):
    monkeypatch.delenv("HERMES_AGENT_MODE", raising=False)
    monkeypatch.setenv("HERMES_AGENT_CLI", "fake-hermes")

    class Completed:
        returncode = 0
        stdout = "默认 Hermes 回复"
        stderr = ""

    def fake_run(cmd, check, capture_output, text, timeout):
        assert cmd[0] == "fake-hermes"
        assert cmd[1] == "-z"
        assert "用户问题" in cmd[2]
        return Completed()

    monkeypatch.setattr("app.services.hermes_bridge.subprocess.run", fake_run)
    result = HermesAgentBridge().ask("SOFC 适合数据中心吗")
    assert result.status == "agent_connected"
    assert result.mode == "cli"
    assert result.response == "默认 Hermes 回复"


def test_bridge_cli_success(monkeypatch):
    monkeypatch.setenv("HERMES_AGENT_MODE", "cli")
    monkeypatch.setenv("HERMES_AGENT_CLI", "fake-hermes")

    class Completed:
        returncode = 0
        stdout = "真实 agent 回复"
        stderr = ""

    def fake_run(cmd, check, capture_output, text, timeout):
        assert cmd[0] == "fake-hermes"
        assert cmd[1] == "-z"
        assert "用户问题" in cmd[2]
        return Completed()

    monkeypatch.setattr("app.services.hermes_bridge.subprocess.run", fake_run)
    result = HermesAgentBridge().ask("问题", "portal")
    assert result.status == "agent_connected"
    assert result.mode == "cli"
    assert result.response == "真实 agent 回复"


def test_bridge_cli_error(monkeypatch):
    monkeypatch.setenv("HERMES_AGENT_MODE", "cli")

    class Completed:
        returncode = 2
        stdout = ""
        stderr = "boom"

    def fake_run(*_args, **_kwargs):
        return Completed()

    monkeypatch.setattr("app.services.hermes_bridge.subprocess.run", fake_run)
    result = HermesAgentBridge().ask("SOFC")
    assert result.status == "error"
    assert result.error == "boom"


def test_bridge_http_json(monkeypatch):
    monkeypatch.setenv("HERMES_AGENT_MODE", "http")
    monkeypatch.setenv("HERMES_AGENT_HTTP_URL", "http://readonly/query")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"answer":"ok","confidence":"medium","verified_facts":[]}'

    def fake_urlopen(*_args, **_kwargs):
        return Response()

    monkeypatch.setattr("app.services.hermes_bridge.urlrequest.urlopen", fake_urlopen)
    result = HermesAgentBridge().ask("SOFC")
    assert result.status == "agent_connected"
    assert result.mode == "http"
    assert result.response == "ok"
    assert result.extra is not None
    assert result.extra["confidence"] == "medium"


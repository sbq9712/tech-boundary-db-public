"""Deployment contract tests for the integrated BoundaryDB stack.

These are intentionally text-level tests: they catch the class of regression where
new QA/upload code exists in the repository but normal deployment silently starts an
old pre-migration image or builds a canonical-qa image without the migrated modules.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_defaults_to_integrated_service_images():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    # 离线交付集 server-20261004：qa=1008（含 TECHDB_QA_LLM_BASE_URL 空串回落）、
    # api=agent=1018（6307112）、web=1016。默认值必须指向已验收 tag，杜绝静默回退旧镜像。
    assert "techdb-canonical-qa:${TECHDB_QA_IMAGE_TAG:-1008}" in compose
    assert "techdb-api:${TECHDB_API_IMAGE_TAG:-1019}" in compose
    assert "techdb-readonly-agent:${TECHDB_AGENT_IMAGE_TAG:-1019}" in compose
    assert "techdb-web:${TECHDB_WEB_IMAGE_TAG:-1016}" in compose
    assert "TECHDB_QA_IMAGE_TAG:-0801" not in compose
    assert "TECHDB_API_IMAGE_TAG:-0801" not in compose
    for stale in ("TECHDB_QA_IMAGE_TAG:-1001", "TECHDB_API_IMAGE_TAG:-1001",
                  "TECHDB_AGENT_IMAGE_TAG:-1001", "TECHDB_WEB_IMAGE_TAG:-1001"):
        assert stale not in compose


def test_deploy_script_honors_per_service_tags():
    deploy = (ROOT / "deploy.sh").read_text(encoding="utf-8")
    for name in (
        "TECHDB_QA_IMAGE_TAG",
        "TECHDB_API_IMAGE_TAG",
        "TECHDB_AGENT_IMAGE_TAG",
        "TECHDB_WEB_IMAGE_TAG",
    ):
        assert name in deploy
    assert "techdb-canonical-qa:0801" not in deploy
    assert 'APP_IMAGES=("techdb-api:0801"' not in deploy
    for name, tag in (
        ("TECHDB_QA_IMAGE_TAG", "1008"),
        ("TECHDB_API_IMAGE_TAG", "1019"),
        ("TECHDB_AGENT_IMAGE_TAG", "1019"),
        ("TECHDB_WEB_IMAGE_TAG", "1016"),
    ):
        assert f"{name}:-{tag}}}\"" in deploy


def test_deploy_script_asserts_incremental_index_ready():
    # canonical-qa 就绪断言必须覆盖增量索引（uploads 增量融合链路），否则
    # 恢复后 incremental 索引缺失时 deploy.sh 仍报成功。
    deploy = (ROOT / "deploy.sh").read_text(encoding="utf-8")
    assert "incremental_index_ready" in deploy
    assert "incremental_corrupt" in deploy


def test_db_backup_packs_uploads_via_container():
    # uploads 子目录由容器以 root 属主写入，宿主 tar 会 Permission denied；
    # 必须经 alpine 临时容器打包（离线交付实测踩坑）。
    backup = (ROOT / "scripts" / "db_backup.sh").read_text(encoding="utf-8")
    assert "alpine:3" in backup
    assert '-v "${UPLOAD_PATH}:/data:ro"' in backup
    host_tar = 'tar --exclude=\'./.incoming\' -C "$UPLOAD_PATH"'
    assert host_tar not in backup


def test_deploy_missing_image_hint_points_to_release():
    deploy = (ROOT / "deploy.sh").read_text(encoding="utf-8")
    assert "docker-images 分支" not in deploy
    assert "server-20261004" in deploy


def test_release_image_contains_full_migrated_qa_chain():
    dockerfile = (
        ROOT / "services" / "canonical-qa" / "qa-backend" / "Dockerfile.release"
    ).read_text(encoding="utf-8")
    required_modules = (
        "record_ops.py",
        "graph_fragment.py",
        "answer_chain.py",
        "epistemic.py",
        "verifier.py",
        "claim_mapping.py",
        "citation_grounding.py",
        "numeric_facts.py",
        "primary_evidence.py",
        "answer_status.py",
        "knowledge_boundary.py",
        "answer_repair.py",
        "provenance.py",
        "evidence_metadata.py",
        "runtime_safety.py",
    )
    for module in required_modules:
        assert module in dockerfile


def test_nginx_long_timeout_scoped_to_sse_only():
    """SSE 专属长超时（2026-10-03 network error 修复 + Codex P3 收窄）。

    1800s 只允许出现在流式端点的 location 块内；普通 /api/ 维持 300s，
    防止心跳机制把真实卡死的普通请求无差别续命。
    """
    import re

    conf = (ROOT / "nginx.conf").read_text(encoding="utf-8")
    blocks = re.findall(
        r"location\s+([^\{]+)\{([^{}]*)\}", conf, flags=re.S
    )
    assert blocks, "nginx.conf 应至少包含一个 location 块"
    seen_sse = False
    for header, body in blocks:
        header = header.strip()
        if re.search(r"/api/\(assistant/stream\|breadth/qa/chat/stream\)", header):
            seen_sse = True
            assert "proxy_read_timeout 1800s" in body, header
            assert "proxy_send_timeout 1800s" in body, header
            assert "proxy_buffering off" in body, header
        elif header == "/api/":
            assert "proxy_read_timeout 300s" in body, header
            assert "proxy_read_timeout 1800s" not in body, header
    assert seen_sse, "SSE 端点应有独立 location 承载 1800s 超时"

"""Deployment contract tests for the integrated BoundaryDB stack.

These are intentionally text-level tests: they catch the class of regression where
new QA/upload code exists in the repository but normal deployment silently starts an
old pre-migration image or builds a canonical-qa image without the migrated modules.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_defaults_to_integrated_service_images():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "techdb-canonical-qa:${TECHDB_QA_IMAGE_TAG:-1001}" in compose
    assert "techdb-api:${TECHDB_API_IMAGE_TAG:-1001}" in compose
    assert "techdb-readonly-agent:${TECHDB_AGENT_IMAGE_TAG:-1001}" in compose
    assert "techdb-web:${TECHDB_WEB_IMAGE_TAG:-1001}" in compose
    assert "TECHDB_QA_IMAGE_TAG:-0801" not in compose
    assert "TECHDB_API_IMAGE_TAG:-0801" not in compose


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

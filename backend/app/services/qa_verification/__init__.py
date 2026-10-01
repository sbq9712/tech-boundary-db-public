"""legacy_hybrid 答案侧真实核验链——backend 侧包（五.1，2026-09-30）。

与 services/canonical-qa/qa-backend/answer_chain.py 互为孪生：核验模块
（epistemic/verifier/claim_mapping/citation_grounding/numeric_facts/
answer_status/knowledge_boundary/answer_repair/provenance）自
tech-db/qa-backend 原样移植，仅 import 行机械差异；编排层 answer_chain
逻辑逐字节相同（此处的版本从 canonical-qa 侧复制后改包内相对 import）。
"""
from app.services.qa_verification.answer_chain import (  # noqa: F401
    ANSWER_CHAIN_VERSION,
    build_rewrite_prompt,
    classify_or_empty,
    compact_for_payload,
    detect_refusal,
    epistemic_prompt,
    run_answer_verification,
)

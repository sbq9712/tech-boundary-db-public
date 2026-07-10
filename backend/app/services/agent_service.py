"""Agent service with streaming SSE support and thinking process visibility.

Core flow:
1. Retrieve: knowledge_base markdown + sources table + parameter_observations
2. Build prompt: retrieval results + conversation history
3. Stream LLM response via SSE with three event types:
   - status: stage updates (retrieving, analyzing, generating)
   - token: real-time typing effect
   - done: structured metadata (citations, recommendations)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import AsyncIterator

import httpx
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from app.models.source import Source
from app.models.parameter_observation import ParameterObservation
from app.models.knowledge_artifact import KnowledgeArtifact
from app.models.conversation import ConversationSession, ConversationMessage


KNOWLEDGE_BASE_PATH = Path(os.getenv("TECHDB_KB_PATH", "/knowledge-base"))
AI_API_KEY = os.getenv("TECHDB_AGENT_API_KEY", os.getenv("CUSTOM_OPENAI_API_KEY", "")).strip()
AI_BASE_URL = os.getenv("TECHDB_AGENT_BASE_URL", "https://api.xiaowang886.xyz/v1").rstrip("/")
AI_MODEL = os.getenv("TECHDB_AGENT_MODEL", "claude-opus-4-8")
AI_TIMEOUT = int(os.getenv("TECHDB_AGENT_TIMEOUT_SECONDS", "120"))
AI_MAX_RETRIES = int(os.getenv("TECHDB_AGENT_MAX_RETRIES", "2"))
AI_RETRY_BASE_DELAY_SECONDS = float(os.getenv("TECHDB_AGENT_RETRY_BASE_DELAY_SECONDS", "2"))


def _parse_allowed_models() -> list[str]:
    """Return the model choices exposed to the portal UI."""
    raw = os.getenv("TECHDB_AGENT_ALLOWED_MODELS", "")
    configured = [item.strip() for item in raw.split(",") if item.strip()]
    defaults = [AI_MODEL, "glm-4.5-flash"]
    models: list[str] = []
    for model in configured + defaults:
        if model and model not in models:
            models.append(model)
    return models


AI_ALLOWED_MODELS = _parse_allowed_models()


def get_available_models() -> dict:
    """Expose model choices without leaking credentials or provider details."""
    return {"default_model": AI_MODEL, "models": AI_ALLOWED_MODELS}


def resolve_model(selected_model: str | None) -> str:
    """Validate a user-selected model and fall back to the configured default."""
    model = (selected_model or AI_MODEL).strip()
    if model not in AI_ALLOWED_MODELS:
        raise ValueError(f"Unsupported model: {model}")
    return model

logger = logging.getLogger(__name__)


_CJK_STOPWORDS = set("的了是在为和与及或也都就还把被让使向从对由以至")


def _normalize_query(query: str) -> list[str]:
    """Extract search terms from query, including CJK bigrams for Chinese text."""
    # Insert space between ASCII and CJK character transitions
    text = re.sub(r"([A-Za-z0-9])([^\x00-\x7F])", r"\1 \2", query)
    text = re.sub(r"([^\x00-\x7F])([A-Za-z0-9])", r"\1 \2", text)
    normalized = re.sub(r"[\s/，。；;:：、（）()\[\]{}%]+", " ", text.lower())
    terms = [term for term in normalized.split() if len(term) >= 2]

    # Extract CJK bigrams — without this, a query like "作为数据中心电源"
    # stays as one long string that never matches anything in the KB.
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", query)
    for i in range(len(cjk_chars) - 1):
        c1, c2 = cjk_chars[i], cjk_chars[i + 1]
        if c1 not in _CJK_STOPWORDS and c2 not in _CJK_STOPWORDS:
            bigram = c1 + c2
            if bigram not in terms:
                terms.append(bigram)

    return terms


def _search_knowledge_base(query: str, limit: int = 8) -> list[dict]:
    """Full-text search in knowledge base markdown files."""
    if not KNOWLEDGE_BASE_PATH.exists():
        return []

    terms = _normalize_query(query)
    results: list[tuple[int, Path, str]] = []

    for path in KNOWLEDGE_BASE_PATH.rglob("*.md"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[:100000]
        except OSError:
            continue

        haystack = f"{path.name}\n{text}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score > 0:
            results.append((score, path, text))

    results.sort(key=lambda x: x[0], reverse=True)

    docs = []
    for score, path, text in results[:limit]:
        # Extract first heading as title
        first_heading = next(
            (line.strip("# ").strip() for line in text.splitlines() if line.startswith("#")),
            path.stem
        )
        # Snippet around first match
        snippet_start = 0
        for term in terms:
            idx = text.lower().find(term)
            if idx >= 0:
                snippet_start = max(0, idx - 100)
                break
        snippet = text[snippet_start:snippet_start + 600].replace("\n", " ").strip()

        docs.append({
            "type": "knowledge_base",
            "title": first_heading,
            "path": str(path.relative_to(KNOWLEDGE_BASE_PATH)),
            "snippet": snippet,
            "score": score,
        })

    return docs


def _search_sources(db: Session, query: str, limit: int = 10) -> list[dict]:
    """Full-text search across source title, source_name, and domain."""
    terms = _normalize_query(query)

    # Build ILIKE filters across multiple fields for each term
    filters = []
    for term in terms:
        filters.append(Source.title.ilike(f"%{term}%"))
        filters.append(Source.source_name.ilike(f"%{term}%"))
        filters.append(Source.domain.ilike(f"%{term}%"))

    stmt = (
        select(Source)
        .where(or_(*filters))
        .order_by(Source.captured_at.desc())
        .limit(limit)
    )

    rows = db.scalars(stmt).all()

    return [
        {
            "type": "source",
            "id": str(s.id),
            "title": s.title,
            "source_type": s.source_type,
            "url": s.url_or_path,
            "source_name": s.source_name,
            "domain": s.domain,
            "reliability_rating": s.reliability_rating,
        }
        for s in rows
    ]


def _search_parameters(db: Session, query: str, limit: int = 10) -> list[dict]:
    """Search parameter observations by parameter_name or scenario."""
    terms = _normalize_query(query)
    
    filters = []
    for term in terms:
        filters.append(ParameterObservation.parameter_name.ilike(f"%{term}%"))
        filters.append(ParameterObservation.scenario.ilike(f"%{term}%"))
        filters.append(ParameterObservation.condition_text.ilike(f"%{term}%"))
    
    stmt = (
        select(ParameterObservation)
        .where(or_(*filters))
        .where(ParameterObservation.verification_status.in_(["human_checked", "machine_extracted"]))
        .order_by(ParameterObservation.created_at.desc())
        .limit(limit)
    )
    
    rows = db.scalars(stmt).all()
    
    return [
        {
            "type": "parameter",
            "id": str(p.id),
            "parameter_name": p.parameter_name,
            "parameter_type": p.parameter_type,
            "value_range": f"{p.value_min}-{p.value_max} {p.unit}" if p.value_min and p.value_max else p.value_text,
            "condition": p.condition_text,
            "scenario": p.scenario,
            "verification_status": p.verification_status,
        }
        for p in rows
    ]


def _build_prompt(query: str, retrieval_results: dict, history: list[dict]) -> list[dict]:
    """Build messages for LLM with retrieval context and conversation history."""
    
    # System prompt
    system_content = """你是技术边界数据库的专业 AI 助手，专注于清洁能源、固态氧化物电池（SOFC/SOC）、储能等前沿技术的调研与分析。

你的职责：
1. 基于检索到的知识库文档、文献来源和参数数据回答用户问题
2. 引用具体数据时给出来源（知识库文档、文献标题、参数观测 ID）
3. 区分"已验证事实"vs"推测"，明确标注不确定信息
4. 提供参数范围时说明工况条件（温度、压力、材料等）
5. 如果检索结果不足以回答问题，明确说明缺失的信息

语气：专业、严谨、简洁，适合技术决策层阅读。"""

    # Retrieval context
    context_parts = []
    
    if retrieval_results.get("knowledge_base"):
        kb_docs = retrieval_results["knowledge_base"]
        context_parts.append(f"## 知识库文档（{len(kb_docs)} 篇）\n")
        for i, doc in enumerate(kb_docs, 1):
            context_parts.append(f"{i}. **{doc['title']}** ({doc['path']})\n   摘要: {doc['snippet'][:600]}...\n")
    
    if retrieval_results.get("sources"):
        srcs = retrieval_results["sources"]
        context_parts.append(f"\n## 相关文献来源（{len(srcs)} 条）\n")
        for i, src in enumerate(srcs, 1):
            context_parts.append(
                f"{i}. **{src['title'][:80]}...** ({src['source_type']}, {src['source_name']})\n"
                f"   领域: {src['domain']}, 可靠度: {src['reliability_rating']}\n"
            )
    
    if retrieval_results.get("parameters"):
        params = retrieval_results["parameters"]
        context_parts.append(f"\n## 参数事实（{len(params)} 条）\n")
        for i, p in enumerate(params, 1):
            context_parts.append(
                f"{i}. **{p['parameter_name']}**: {p['value_range']}\n"
                f"   工况: {p['condition']}\n"
                f"   场景: {p['scenario']}\n"
                f"   验证状态: {p['verification_status']}\n"
            )
    
    context_text = "".join(context_parts) if context_parts else "（无相关检索结果）"
    
    # Build message list
    messages = [
        {"role": "system", "content": system_content}
    ]
    
    # Add conversation history (last 10 exchanges)
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Add current query with retrieval context
    user_message = f"# 检索上下文\n{context_text}\n\n# 用户问题\n{query}"
    messages.append({"role": "user", "content": user_message})
    
    return messages


def _match_dashboards(db: Session, query: str, limit: int = 3) -> list[dict]:
    """Match deep-research dashboards to the query by keyword overlap.

    Scores each knowledge_artifact by how many query keywords appear in its
    title, tech_node aliases, and related parameter names.
    """
    artifacts = db.query(KnowledgeArtifact).filter(
        KnowledgeArtifact.artifact_type == "deep_research_note",
        KnowledgeArtifact.status == "active",
    ).all()

    if not artifacts:
        return []

    # Normalize query into keywords (CJK chars + latin words)
    query_lower = query.lower()
    # Extract meaningful keywords (length >= 2 for CJK, >= 3 for latin)
    cjk_chars = set(c for c in query if '\u4e00' <= c <= '\u9fff')
    latin_words = set(w for w in re.split(r'[\s,，。、；;？?！!()（）]+', query_lower) if len(w) >= 3)
    keywords = cjk_chars | latin_words

    if not keywords:
        return []

    scored = []
    for art in artifacts:
        # Build searchable text from title + tech node aliases
        title_lower = (art.title or "").lower()
        # We don't have direct access to tech node aliases without a join,
        # but the title + vault_path contains the key terms
        search_text = f"{title_lower} {(art.vault_path or '').lower()}"

        score = sum(1 for kw in keywords if kw in search_text)
        if score > 0:
            dash_id = (art.stable_id or "").replace("ART-20260709-", "").lower()
            scored.append((score, {
                "id": dash_id,
                "name": (art.title or "").replace("_技术边界", "").replace("_", " "),
                "stable_id": art.stable_id,
                "vault_path": art.vault_path,
            }))

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


async def stream_agent_response(
    query: str,
    session_id: str | None,
    db: Session,
    selected_model: str | None = None,
) -> AsyncIterator[str]:
    """
    Stream agent response with SSE format.
    
    Yields SSE events:
    - event: status, data: {"stage": "retrieving", "message": "..."}
    - event: token, data: {"content": "..."}
    - event: done, data: {"citations": [...], "session_id": "..."}
    """
    
    # Stage 1: Retrieval
    yield f'event: status\ndata: {json.dumps({"stage": "retrieving", "message": "🔍 正在检索知识库..."}, ensure_ascii=False)}\n\n'
    
    kb_results = _search_knowledge_base(query, limit=8)

    yield f'event: status\ndata: {json.dumps({"stage": "retrieving", "message": f"📊 找到 {len(kb_results)} 篇知识库文档"}, ensure_ascii=False)}\n\n'

    sources_results = _search_sources(db, query, limit=10)
    params_results = _search_parameters(db, query, limit=10)
    
    yield f'event: status\ndata: {json.dumps({"stage": "retrieving", "message": f"📚 找到 {len(sources_results)} 条文献、{len(params_results)} 条参数"}, ensure_ascii=False)}\n\n'
    
    retrieval_results = {
        "knowledge_base": kb_results,
        "sources": sources_results,
        "parameters": params_results,
    }
    
    # Load conversation history if session_id provided
    history = []
    if session_id:
        stmt = (
            select(ConversationMessage)
            .join(ConversationSession)
            .where(ConversationSession.id == session_id)
            .order_by(ConversationMessage.created_at.asc())
            .limit(20)
        )
        msgs = db.scalars(stmt).all()
        history = [{"role": m.role, "content": m.content} for m in msgs]
    
    # Stage 2: Build prompt
    yield f'event: status\ndata: {json.dumps({"stage": "analyzing", "message": "🤔 正在分析..."}, ensure_ascii=False)}\n\n'
    
    messages = _build_prompt(query, retrieval_results, history)
    
    # Stage 3: Stream LLM response
    yield f'event: status\ndata: {json.dumps({"stage": "generating", "message": "✍️ 正在生成回答..."}, ensure_ascii=False)}\n\n'
    
    full_response = ""
    
    request_model = resolve_model(selected_model)
    request_payload = {
        "model": request_model,
        "messages": messages,
        "stream": True,
        "temperature": 0.3,
    }
    prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)
    prompt_rough_tokens = max(1, prompt_chars // 4)

    try:
        async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
            for attempt in range(AI_MAX_RETRIES + 1):
                try:
                    async with client.stream(
                        "POST",
                        f"{AI_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {AI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=request_payload,
                    ) as response:
                        if response.status_code == 429:
                            body = (await response.aread()).decode("utf-8", errors="replace")[:1000]
                            logger.warning(
                                "LLM 429 from upstream: attempt=%s/%s model=%s base_url=%s "
                                "messages=%s prompt_chars=%s prompt_rough_tokens=%s body=%s",
                                attempt + 1,
                                AI_MAX_RETRIES + 1,
                                request_model,
                                AI_BASE_URL,
                                len(messages),
                                prompt_chars,
                                prompt_rough_tokens,
                                body,
                            )
                            if attempt < AI_MAX_RETRIES:
                                delay = AI_RETRY_BASE_DELAY_SECONDS * (attempt + 1)
                                yield f'event: status\ndata: {json.dumps({"stage": "retrying", "message": f"模型服务繁忙，{delay:g} 秒后重试..."}, ensure_ascii=False)}\n\n'
                                await asyncio.sleep(delay)
                                continue
                            yield f'event: error\ndata: {json.dumps({"error": "LLM API rate limit exceeded, please retry later"}, ensure_ascii=False)}\n\n'
                            return

                        response.raise_for_status()

                        async for line in response.aiter_lines():
                            if not line.strip() or line.strip() == "data: [DONE]":
                                continue

                            if line.startswith("data: "):
                                try:
                                    chunk_data = json.loads(line[6:])
                                    delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                                    content = delta.get("content", "")

                                    if content:
                                        full_response += content
                                        yield f'event: token\ndata: {json.dumps({"content": content}, ensure_ascii=False)}\n\n'

                                except json.JSONDecodeError:
                                    continue
                        break
                except httpx.HTTPStatusError as e:
                    body = e.response.text[:1000]
                    logger.warning(
                        "LLM HTTP error from upstream: status=%s model=%s base_url=%s "
                        "messages=%s prompt_chars=%s prompt_rough_tokens=%s body=%s",
                        e.response.status_code,
                        request_model,
                        AI_BASE_URL,
                        len(messages),
                        prompt_chars,
                        prompt_rough_tokens,
                        body,
                    )
                    yield f'event: error\ndata: {json.dumps({"error": f"LLM API error: {e.response.status_code}"}, ensure_ascii=False)}\n\n'
                    return
    except Exception as e:
        logger.exception(
            "LLM call failed: model=%s base_url=%s messages=%s prompt_chars=%s prompt_rough_tokens=%s",
            request_model,
            AI_BASE_URL,
            len(messages),
            prompt_chars,
            prompt_rough_tokens,
        )
        yield f'event: error\ndata: {json.dumps({"error": f"LLM call failed: {str(e)}"}, ensure_ascii=False)}\n\n'
        return
    
    # Stage 4: Done - send citations and metadata
    citations = []
    
    # Add knowledge base citations
    for doc in kb_results[:3]:
        citations.append({
            "type": "knowledge_base",
            "title": doc["title"],
            "path": doc["path"],
        })
    
    # Add source citations
    for src in sources_results[:5]:
        citations.append({
            "type": "source",
            "title": src["title"],
            "source_type": src["source_type"],
            "url": src.get("url"),
        })
    
    # Add parameter citations
    for param in params_results[:3]:
        citations.append({
            "type": "parameter",
            "parameter_name": param["parameter_name"],
            "value_range": param["value_range"],
            "verification_status": param["verification_status"],
        })

    # Match deep-research dashboards for panel recommendations
    dashboard_recs = _match_dashboards(db, query, limit=3)
    hot_intel = sources_results[:3] if sources_results else []
    
    done_data = {
        "response": full_response,
        "citations": citations,
        "session_id": session_id,
        "model": request_model,
        "retrieval_summary": {
            "knowledge_base": len(kb_results),
            "sources": len(sources_results),
            "parameters": len(params_results),
        },
        "panel_recommendations": {
            "hot_intel": hot_intel,
            "parameter_boundaries": params_results[:4],
            "alert_intel": [],
            "dashboard_links": dashboard_recs,
        }
    }
    
    yield f'event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n'

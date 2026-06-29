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

import json
import os
import re
from pathlib import Path
from typing import AsyncIterator

import httpx
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from app.models.source import Source
from app.models.parameter_observation import ParameterObservation
from app.models.conversation import ConversationSession, ConversationMessage


KNOWLEDGE_BASE_PATH = Path(os.getenv("TECHDB_KB_PATH", "/mnt/d/##EDMUNDS/知识库"))
AI_API_KEY = os.getenv("TECHDB_AGENT_API_KEY", os.getenv("CUSTOM_OPENAI_API_KEY", "")).strip()
AI_BASE_URL = os.getenv("TECHDB_AGENT_BASE_URL", "https://api.xiaowang886.xyz/v1").rstrip("/")
AI_MODEL = os.getenv("TECHDB_AGENT_MODEL", "claude-opus-4-8")
AI_TIMEOUT = int(os.getenv("TECHDB_AGENT_TIMEOUT_SECONDS", "120"))


def _normalize_query(query: str) -> list[str]:
    """Extract search terms from query."""
    normalized = re.sub(r"[\s/，。；;:：、（）()\[\]{}]+", " ", query.lower())
    return [term for term in normalized.split() if len(term) >= 2]


def _search_knowledge_base(query: str, limit: int = 5) -> list[dict]:
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
        snippet = text[snippet_start:snippet_start + 400].replace("\n", " ").strip()
        
        docs.append({
            "type": "knowledge_base",
            "title": first_heading,
            "path": str(path.relative_to(KNOWLEDGE_BASE_PATH)),
            "snippet": snippet,
            "score": score,
        })
    
    return docs


def _search_sources(db: Session, query: str, limit: int = 10) -> list[dict]:
    """Full-text search in sources table (title only for now, can add FTS5 later)."""
    terms = _normalize_query(query)
    
    # Build ILIKE filters for each term
    filters = []
    for term in terms:
        filters.append(Source.title.ilike(f"%{term}%"))
    
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
            context_parts.append(f"{i}. **{doc['title']}** ({doc['path']})\n   摘要: {doc['snippet'][:200]}...\n")
    
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


async def stream_agent_response(
    query: str,
    session_id: str | None,
    db: Session,
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
    
    kb_results = _search_knowledge_base(query, limit=5)
    
    yield f'event: status\ndata: {json.dumps({"stage": "retrieving", "message": f"📊 找到 {len(kb_results)} 篇知识库文档"}, ensure_ascii=False)}\n\n'
    
    sources_results = _search_sources(db, query, limit=8)
    params_results = _search_parameters(db, query, limit=8)
    
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
    
    async with httpx.AsyncClient(timeout=AI_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{AI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "messages": messages,
                "stream": True,
                "temperature": 0.3,
            },
        ) as response:
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
    
    done_data = {
        "response": full_response,
        "citations": citations,
        "session_id": session_id,
        "retrieval_summary": {
            "knowledge_base": len(kb_results),
            "sources": len(sources_results),
            "parameters": len(params_results),
        }
    }
    
    yield f'event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n'

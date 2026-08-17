from __future__ import annotations

import os
import re
import httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.info_item import InfoItem
from app.services.chatbot_index import ChatbotIndexAdapter

app = FastAPI(title="TechDB Readonly Agent", version="0.2.0")

KNOWLEDGE_BASE_PATH = Path(os.getenv("TECHDB_KB_PATH", "/knowledge-base"))
CHATBOT_PACKAGE_PATH = Path(os.getenv("TECHDB_CHATBOT_PACKAGE_PATH", "/chatbot-integration-package"))
MAX_DOC_CHARS = int(os.getenv("TECHDB_KB_MAX_DOC_CHARS", "240000"))
AI_API_KEY = os.getenv("TECHDB_AGENT_API_KEY", "").strip()
AI_BASE_URL = os.getenv("TECHDB_AGENT_BASE_URL", "https://aigate.catl.com/v1").rstrip("/")
AI_MODEL = os.getenv("TECHDB_AGENT_MODEL", "GLM-5.2")
AI_TIMEOUT_SECONDS = int(os.getenv("TECHDB_AGENT_AI_TIMEOUT_SECONDS", "180"))


class QueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    context: str = "portal"


def _terms(query: str) -> list[str]:
    normalized = re.sub(r"[\s/，。；;:：、（）()\[\]{}]+", " ", query.lower())
    return [term for term in normalized.split() if len(term) >= 2]


def _markdown_files() -> list[Path]:
    if not KNOWLEDGE_BASE_PATH.exists():
        return []
    return sorted(
        path for path in KNOWLEDGE_BASE_PATH.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
    )


def _read_doc(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:MAX_DOC_CHARS]
    except OSError:
        return ""


def _snippet(text: str, terms: list[str], max_len: int = 260) -> str:
    lower = text.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    start = max(min(positions) - 80, 0) if positions else 0
    snippet = text[start:start + max_len].replace("\n", " ").strip()
    return snippet


def _search_kb(query: str, limit: int = 5) -> list[dict[str, Any]]:
    terms = _terms(query)
    results: list[tuple[int, Path, str]] = []
    for path in _markdown_files():
        text = _read_doc(path)
        if not text:
            continue
        haystack = f"{path.name}\n{text}".lower()
        score = sum(haystack.count(term) for term in terms)
        if score:
            results.append((score, path, text))
    results.sort(key=lambda row: row[0], reverse=True)
    docs = []
    for score, path, text in results[:limit]:
        rel_path = str(path.relative_to(KNOWLEDGE_BASE_PATH))
        first_heading = next((line.strip("# ").strip() for line in text.splitlines() if line.startswith("#")), path.stem)
        docs.append({
            "id": rel_path,
            "title": first_heading or path.stem,
            "path": rel_path,
            "score": score,
            "snippet": _snippet(text, terms),
            "source_type": "obsidian_markdown",
        })
    return docs


def _item_text(item: InfoItem) -> str:
    parts = [
        item.title or "",
        item.content or "",
        " ".join(item.source_types or []),
        " ".join(item.info_types or []),
        " ".join(item.tags or []),
        " ".join(rel.domain_id for rel in item.domains),
    ]
    return " ".join(parts).lower()


def _search_info_items(query: str, limit: int = 5) -> list[InfoItem]:
    terms = _terms(query)
    with SessionLocal() as db:
        items = db.scalars(
            select(InfoItem)
            .options(selectinload(InfoItem.domains))
            .order_by(InfoItem.importance_score.desc(), InfoItem.published_at.desc().nullslast())
            .limit(200)
        ).all()
    if not terms:
        return list(items[:limit])
    scored: list[tuple[int, InfoItem]] = []
    for item in items:
        text = _item_text(item)
        score = sum(text.count(term) for term in terms)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda row: (row[0], row[1].importance_score or 0), reverse=True)
    return [item for _, item in scored[:limit]]


def _dashboard_matches(query: str) -> list[dict[str, Any]]:
    dashboards = [
        {"id": "sofc-soc", "name": "SOFC / SOC", "scope": "数据中心电源、分布式发电、rSOC", "metrics": ["电解质电导率", "堆寿命", "系统效率", "单位投资成本", "燃料利用率"]},
        {"id": "aidc-power", "name": "AIDC 能源系统", "scope": "供电架构、备用电源、热管理", "metrics": ["可用率", "PUE", "电力容量", "审批周期", "备用时长"]},
        {"id": "long-duration-storage", "name": "长时储能", "scope": "液流、压缩空气、热储能、氢储能", "metrics": ["LCOS", "储能时长", "循环寿命", "地理约束", "响应时间"]},
    ]
    text = query.lower()
    return [item for item in dashboards if item["id"].lower() in text or item["name"].lower() in text or any(metric.lower() in text for metric in item["metrics"])] or dashboards[:2]


def _search_chatbot_package(query: str) -> dict[str, Any]:
    try:
        return ChatbotIndexAdapter(CHATBOT_PACKAGE_PATH).search(query).to_dict()
    except Exception as exc:
        return {
            "domains": [],
            "sources": [],
            "parameters": [],
            "citations": [],
            "health": {"package_path": str(CHATBOT_PACKAGE_PATH), "package_mounted": CHATBOT_PACKAGE_PATH.exists()},
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def _build_context(
    kb_docs: list[dict[str, Any]],
    items: list[InfoItem],
    dashboards: list[dict[str, Any]],
    chatbot: dict[str, Any],
) -> str:
    sections: list[str] = []
    chatbot_domains = chatbot.get("domains") or []
    chatbot_sources = chatbot.get("sources") or []
    chatbot_parameters = chatbot.get("parameters") or []
    if chatbot_domains:
        sections.append("## 多领域知识包路由")
        for domain in chatbot_domains[:4]:
            subdomains = "、".join((domain.get("subdomains") or [])[:8])
            sections.append(
                f"- {domain.get('domain')}：score={domain.get('score', 0)}；子领域：{subdomains}"
            )
    if chatbot_sources:
        sections.append("## chatbot_integration_package 来源证据")
        for idx, source in enumerate(chatbot_sources[:4], 1):
            sections.append(
                f"[S{idx}] 标题：{source.get('title')}\n"
                f"领域：{source.get('domain')} / {source.get('subdomain')}\n"
                f"来源：{source.get('source_name') or source.get('source_type')}；URL：{source.get('url') or '无'}\n"
                f"摘要：{(source.get('summary') or '')[:260]}"
            )
    if chatbot_parameters:
        sections.append("## chatbot_integration_package 参数事实")
        for idx, parameter in enumerate(chatbot_parameters[:4], 1):
            value = parameter.get("value")
            unit = parameter.get("unit") or ""
            sections.append(
                f"[P{idx}] 对象：{parameter.get('object_name')}\n"
                f"领域：{parameter.get('domain')} / {parameter.get('subdomain')}\n"
                f"参数：{parameter.get('parameter_name')} = {value}{unit}\n"
                f"证据：{(parameter.get('evidence_text') or '')[:260]}\n"
                f"警告：{parameter.get('comparability_warning') or '无'}\n"
                f"URL：{parameter.get('source_url') or '无'}"
            )
    if kb_docs:
        sections.append("## 知识库文档")
        for idx, doc in enumerate(kb_docs[:2], 1):
            sections.append(
                f"[{idx}] 标题：{doc['title']}\n路径：{doc['path']}\n片段：{doc['snippet'][:260]}"
            )
    if items:
        sections.append("## 情报数据库")
        for idx, item in enumerate(items[:2], 1):
            sections.append(
                f"[{idx}] 标题：{item.title}\n来源：{item.source_url or '无'}\n类型：{', '.join(item.info_types or [])}\n重要度：{item.importance_score}"
            )
    if dashboards:
        sections.append("## 相关仪表盘")
        for dashboard in dashboards[:2]:
            sections.append(
                f"- {dashboard['name']}：{dashboard['scope']}；指标：{'、'.join(dashboard['metrics'][:5])}"
            )
    return "\n\n".join(sections)[:5200]


def _panel_recommendations(
    items: list[InfoItem],
    dashboards: list[dict[str, Any]],
    chatbot: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    chatbot = chatbot or {}
    hot_intel = [
        {
            "title": item.title,
            "summary": item.content[:120] if item.content else "",
            "source_url": item.source_url,
        }
        for item in items[:2]
    ]
    alert_intel = [
        {
            "title": item.title,
            "summary": item.content[:120] if item.content else "",
            "source_url": item.source_url,
        }
        for item in items
        if item.alert_status == "active"
    ][:2]
    dashboard_links = [
        {
            "id": dashboard["id"],
            "name": dashboard["name"],
            "summary": dashboard["scope"],
        }
        for dashboard in dashboards[:2]
    ]
    parameter_boundaries = [
        {
            "title": parameter.get("object_name") or parameter.get("parameter_name"),
            "name": parameter.get("parameter_name"),
            "value": f"{parameter.get('value') or ''}{parameter.get('unit') or ''}",
            "domain": parameter.get("domain"),
            "summary": parameter.get("evidence_text"),
        }
        for parameter in (chatbot.get("parameters") or [])[:4]
    ]
    return {
        "hot_intel": hot_intel,
        "parameter_boundaries": parameter_boundaries,
        "alert_intel": alert_intel,
        "dashboard_links": dashboard_links,
    }


def _generate_ai_answer(
    query: str,
    kb_docs: list[dict[str, Any]],
    items: list[InfoItem],
    dashboards: list[dict[str, Any]],
    chatbot: dict[str, Any],
) -> tuple[str, str, str | None]:
    if not AI_API_KEY:
        return "", "low", "missing_openai_api_key"
    context = _build_context(kb_docs, items, dashboards, chatbot)
    if not context.strip():
        return "", "low", "no_retrieved_context"
    system = (
        "你是技术边界数据库的只读知识库问答 Agent。"
        "只能基于提供的检索上下文回答，不能编造未给出的数据、文献或结论。"
        "回答要面向技术尽调/行业研究，直接、审慎，区分已验证事实、推测和缺失数据。"
        "不得提出会写文件、修改数据库、运行命令的动作。"
    )
    user = (
        f"用户问题：{query}\n\n"
        f"检索上下文：\n{context}\n\n"
        "请给出中文回答。格式：\n"
        "1. 直接判断\n"
        "2. 已验证事实（每条附引用路径或 URL）\n"
        "3. 推测/解释\n"
        "4. 缺失数据\n"
        "5. 可查看的相关仪表盘\n"
    )
    try:
        with httpx.Client(timeout=AI_TIMEOUT_SECONDS) as client:
            resp = client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 900,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else ""
        return "", "low", f"ai_call_failed: HTTP {exc.response.status_code if exc.response else 'unknown'} {detail}"
    except Exception as exc:
        return "", "low", f"ai_call_failed: {exc.__class__.__name__}"
    try:
        content = payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return "", "low", "ai_response_parse_failed"
    return content, "medium", None


@app.get("/health")
def health() -> dict[str, Any]:
    files = _markdown_files()
    chatbot_health = ChatbotIndexAdapter(CHATBOT_PACKAGE_PATH).health()
    return {
        "status": "ok",
        "agent": "techdb-readonly",
        "knowledge_base_path": str(KNOWLEDGE_BASE_PATH),
        "knowledge_base_mounted": KNOWLEDGE_BASE_PATH.exists(),
        "markdown_files": len(files),
        "chatbot_package": chatbot_health,
        "ai_enabled": bool(AI_API_KEY),
        "ai_model": AI_MODEL if AI_API_KEY else None,
    }


@app.post("/query")
def query(payload: QueryIn) -> dict[str, Any]:
    cleaned_query = payload.query.strip()
    kb_docs = _search_kb(cleaned_query)
    items = _search_info_items(cleaned_query)
    dashboards = _dashboard_matches(cleaned_query)
    chatbot = _search_chatbot_package(cleaned_query)
    verified_facts = [
        {"title": item.title, "importance_score": item.importance_score, "source_types": item.source_types or [], "info_types": item.info_types or [], "domain_ids": [rel.domain_id for rel in item.domains], "source_url": item.source_url}
        for item in items
    ]
    ai_answer, ai_confidence, ai_error = _generate_ai_answer(cleaned_query, kb_docs, items, dashboards, chatbot)
    if ai_answer:
        answer = ai_answer
        confidence = ai_confidence
    elif chatbot.get("sources") or chatbot.get("parameters"):
        source_count = len(chatbot.get("sources") or [])
        parameter_count = len(chatbot.get("parameters") or [])
        domains = "、".join(
            domain.get("domain", "")
            for domain in (chatbot.get("domains") or [])[:3]
            if domain.get("domain")
        )
        answer = (
            f"已在多领域知识包中找到 {source_count} 条来源证据和 {parameter_count} 条参数事实"
            f"{'，候选领域：' + domains if domains else ''}。"
            "当前 AI 回答未生成，先返回检索结果与引用；请查看下方相关文档/参数边界。"
        )
        confidence = "medium"
    elif kb_docs:
        answer = f"已在只读知识库中找到 {len(kb_docs)} 个相关文档，但 AI 回答生成失败，当前仅返回检索结果。"
        confidence = "medium"
    elif items:
        answer = f"已在情报数据库中找到 {len(items)} 条相关情报，但知识库未命中文档，且 AI 回答未生成。"
        confidence = "medium"
    else:
        answer = "未在当前只读知识库或情报数据库中找到足够匹配的信息。"
        confidence = "low"
    return {
        "answer": answer,
        "confidence": confidence,
        "ai_enabled": bool(AI_API_KEY),
        "ai_model": AI_MODEL if AI_API_KEY else None,
        "ai_error": ai_error,
        "verified_facts": verified_facts,
        "chatbot_domains": chatbot.get("domains") or [],
        "chatbot_sources": chatbot.get("sources") or [],
        "chatbot_parameters": chatbot.get("parameters") or [],
        "chatbot_health": chatbot.get("health") or {},
        "chatbot_error": chatbot.get("error"),
        "knowledge_documents": kb_docs,
        "assumptions": [
            "当前只读 agent 读取 chatbot_integration_package 多领域索引、挂载 Markdown 知识库和数据库情报表，不编辑知识库。"
        ],
        "missing_data": [] if (kb_docs or items or chatbot.get("sources") or chatbot.get("parameters")) else ["缺少可直接支撑回答的情报、文档或参数事实。"],
        "related_dashboards": dashboards,
        "panel_recommendations": _panel_recommendations(items, dashboards, chatbot),
        "citations": [doc["path"] for doc in kb_docs]
        + [item.source_url for item in items if item.source_url]
        + [citation for citation in (chatbot.get("citations") or []) if citation],
        "agent": "techdb-readonly",
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

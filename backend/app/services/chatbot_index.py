from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_PACKAGE_PATH = Path(
    os.getenv(
        "TECHDB_CHATBOT_PACKAGE_PATH",
        os.getenv(
            "TECHDB_CHATBOT_PACKAGE",
            "/chatbot-integration-package",
        ),
    )
)

BUILTIN_QUERY_TERMS = [
    "钙钛矿",
    "晶硅",
    "叠层电池",
    "有机光伏",
    "光伏",
    "固态电池",
    "钠离子电池",
    "锂金属电池",
    "锂硫电池",
    "电池回收",
    "电池安全",
    "负极",
    "正极",
    "电解质",
    "隔膜",
    "数据中心",
    "液冷",
    "AI",
    "半导体",
    "机器人",
    "量子信息",
    "关键矿产",
    "稀土",
    "铜",
    "锂",
    "镍",
    "CCUS",
    "地热",
    "核能",
    "氢",
    "氨",
    "甲醇",
    "风能",
    "储能",
    "液流电池",
    "压缩空气储能",
    "热储能",
    "飞轮储能",
    "超级电容器",
    "钢铁",
    "化工",
    "碳市场",
    "石油炼化",
    "建筑",
    "塑料回收",
]


@dataclass(frozen=True)
class ChatbotSearchResult:
    domains: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    parameters: list[dict[str, Any]]
    citations: list[str]
    health: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": self.domains,
            "sources": self.sources,
            "parameters": self.parameters,
            "citations": self.citations,
            "health": self.health,
            "error": self.error,
        }


class ChatbotIndexAdapter:
    """Readonly adapter for chatbot_integration_package indexes.

    The package already contains domain, source, and parameter indexes. This
    adapter intentionally avoids rebuilding a vector store during the local
    release. It gives the agent a stable evidence bundle now, and can later be
    replaced by a stronger retrieval service behind the same contract.
    """

    def __init__(self, package_path: str | Path | None = None) -> None:
        self.package_path = Path(package_path or DEFAULT_PACKAGE_PATH)
        self.index_dir = self.package_path / "indexes"

    @property
    def domain_index_path(self) -> Path:
        return self.index_dir / "domain_index.json"

    @property
    def source_db_path(self) -> Path:
        return self.index_dir / "source_index.sqlite"

    @property
    def parameter_db_path(self) -> Path:
        return self.index_dir / "optimal_parameter_index.sqlite"

    @property
    def parameter_summary_path(self) -> Path:
        return self.index_dir / "parameter_index_summary.json"

    def health(self) -> dict[str, Any]:
        domain_index = _load_domain_index(str(self.domain_index_path))
        parameter_summary = _load_parameter_summary(str(self.parameter_summary_path))
        return {
            "package_path": str(self.package_path),
            "package_mounted": self.package_path.exists(),
            "domain_index_available": self.domain_index_path.exists(),
            "source_db_available": self.source_db_path.exists(),
            "parameter_db_available": self.parameter_db_path.exists(),
            "domain_count": len(domain_index.get("domains", [])),
            "domains": [item.get("domain") for item in domain_index.get("domains", [])],
            "parameter_value_count": parameter_summary.get("total_parameter_values"),
            "generated_at": parameter_summary.get("generated_at"),
        }

    def list_domains(self) -> list[dict[str, Any]]:
        domain_index = _load_domain_index(str(self.domain_index_path))
        domains: list[dict[str, Any]] = []
        for item in domain_index.get("domains", []):
            subdomains = item.get("subdomains") or []
            domains.append(
                {
                    "domain": item.get("domain", ""),
                    "subdomains": [sub.get("subdomain", "") for sub in subdomains],
                    "source_count": sum(int(sub.get("source_count") or 0) for sub in subdomains),
                    "knowledge_unit_count": sum(int(sub.get("knowledge_unit_count") or 0) for sub in subdomains),
                    "parameter_index_available": any(bool(sub.get("parameter_index_available")) for sub in subdomains),
                }
            )
        return domains

    def search(self, query: str, limit: int = 6) -> ChatbotSearchResult:
        health = self.health()
        if not health["package_mounted"]:
            return ChatbotSearchResult([], [], [], [], health, error="chatbot_package_not_mounted")
        terms = self._query_terms(query)
        routed_domains = self._route_domains(query, terms)[:5]
        domain_names = [item["domain"] for item in routed_domains if item.get("score", 0) > 0]
        sources = self._search_sources(terms, domain_names, limit=limit)
        parameters = self._search_parameters(terms, domain_names, limit=limit)
        citations = _dedupe(
            [
                item.get("url") or item.get("source_id") or item.get("title")
                for item in sources
            ]
            + [
                item.get("source_url") or item.get("parameter_id") or item.get("object_name")
                for item in parameters
            ]
        )
        return ChatbotSearchResult(routed_domains, sources, parameters, citations, health)

    def _domain_terms(self) -> list[str]:
        terms: list[str] = []
        for item in self.list_domains():
            if item.get("domain"):
                terms.append(str(item["domain"]))
            terms.extend(str(sub) for sub in item.get("subdomains", []) if sub)
        return _dedupe(terms + BUILTIN_QUERY_TERMS)

    def _query_terms(self, query: str) -> list[str]:
        lower_query = query.lower()
        terms: list[str] = []
        for token in self._domain_terms():
            if token and token.lower() in lower_query:
                terms.append(token)
        terms.extend(re.findall(r"[A-Za-z0-9][A-Za-z0-9+_.-]{1,}", query))
        for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", query):
            if len(phrase) <= 8:
                terms.append(phrase)
        if not terms and query.strip():
            terms.append(query.strip()[:16])
        return _dedupe(terms)[:10]

    def _route_domains(self, query: str, terms: list[str]) -> list[dict[str, Any]]:
        lower_query = query.lower()
        routed: list[dict[str, Any]] = []
        for domain in self.list_domains():
            names = [domain.get("domain", ""), *(domain.get("subdomains") or [])]
            score = 0
            matched: list[str] = []
            for name in names:
                if name and name.lower() in lower_query:
                    score += 5
                    matched.append(name)
            for term in terms:
                term_lower = term.lower()
                if any(term_lower in str(name).lower() for name in names):
                    score += 2
                    matched.append(term)
            routed.append({**domain, "score": score, "matched_terms": _dedupe(matched)})
        return sorted(routed, key=lambda item: (item.get("score", 0), item.get("source_count", 0)), reverse=True)

    def _search_sources(self, terms: list[str], domains: list[str], limit: int) -> list[dict[str, Any]]:
        if not self.source_db_path.exists():
            return []
        where, params = _like_where(
            terms,
            ["title", "summary", "raw_text_preview", "subdomain", "source_name"],
        )
        domain_where, domain_params = _domain_where(domains)
        clauses = [part for part in [where, domain_where] if part]
        sql = (
            "select source_id, source_type, title, publish_date, source_name, url, domain, subdomain, "
            "summary, raw_text_preview, quality_status, need_human_review "
            "from sources"
        )
        if clauses:
            sql += " where " + " and ".join(f"({part})" for part in clauses)
        sql += " limit 300"
        rows = _query_sqlite(self.source_db_path, sql, [*params, *domain_params])
        scored = []
        for row in rows:
            text = " ".join(
                str(row.get(key) or "")
                for key in ["title", "summary", "raw_text_preview", "subdomain", "source_name"]
            )
            base_score = _score_text(text, terms)
            if terms and base_score <= 0:
                continue
            score = base_score
            if row.get("domain") in domains:
                score += 3
            if row.get("quality_status") == "pass":
                score += 1
            if score > 0 or not terms:
                scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "source_id": row.get("source_id"),
                "source_type": row.get("source_type"),
                "title": row.get("title"),
                "publish_date": row.get("publish_date"),
                "source_name": row.get("source_name"),
                "url": row.get("url"),
                "domain": row.get("domain"),
                "subdomain": row.get("subdomain"),
                "summary": row.get("summary") or row.get("raw_text_preview") or "",
                "quality_status": row.get("quality_status"),
                "need_human_review": bool(row.get("need_human_review")),
                "score": score,
            }
            for score, row in scored[:limit]
        ]

    def _search_parameters(self, terms: list[str], domains: list[str], limit: int) -> list[dict[str, Any]]:
        if not self.parameter_db_path.exists():
            return []
        where, params = _like_where(
            terms,
            [
                "object_name",
                "evidence_text",
                "domain",
                "subdomain",
                "technology_route",
                "parameter_name",
                "canonical_parameter_name",
            ],
        )
        domain_where, domain_params = _domain_where(domains)
        clauses = [part for part in [where, domain_where] if part]
        sql = (
            "select parameter_id, source_id, source_type, domain, subdomain, technology_route, "
            "parameter_name, canonical_parameter_name, value_raw, value_numeric, value_text, unit, "
            "object_name, object_type, test_condition_text, comparability_warning, evidence_text, "
            "source_url, publish_date, source_evidence_category, evidence_usage, confidence, need_human_review "
            "from parameter_values"
        )
        if clauses:
            sql += " where " + " and ".join(f"({part})" for part in clauses)
        sql += " limit 400"
        rows = _query_sqlite(self.parameter_db_path, sql, [*params, *domain_params])
        scored = []
        for row in rows:
            text = " ".join(
                str(row.get(key) or "")
                for key in [
                    "object_name",
                    "evidence_text",
                    "subdomain",
                    "technology_route",
                    "parameter_name",
                    "canonical_parameter_name",
                ]
            )
            base_score = _score_text(text, terms)
            if terms and base_score <= 0:
                continue
            score = base_score
            if row.get("domain") in domains:
                score += 3
            if row.get("confidence") == "high":
                score += 1
            if score > 0 or not terms:
                scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "parameter_id": row.get("parameter_id"),
                "source_id": row.get("source_id"),
                "source_type": row.get("source_type"),
                "domain": row.get("domain"),
                "subdomain": row.get("subdomain"),
                "technology_route": row.get("technology_route"),
                "parameter_name": row.get("canonical_parameter_name") or row.get("parameter_name"),
                "value": row.get("value_text") or row.get("value_raw"),
                "value_numeric": row.get("value_numeric"),
                "unit": row.get("unit"),
                "object_name": row.get("object_name"),
                "object_type": row.get("object_type"),
                "test_condition_text": row.get("test_condition_text"),
                "comparability_warning": row.get("comparability_warning"),
                "evidence_text": row.get("evidence_text"),
                "source_url": row.get("source_url"),
                "publish_date": row.get("publish_date"),
                "evidence_category": row.get("source_evidence_category"),
                "evidence_usage": row.get("evidence_usage"),
                "confidence": row.get("confidence"),
                "need_human_review": bool(row.get("need_human_review")),
                "score": score,
            }
            for score, row in scored[:limit]
        ]


@lru_cache(maxsize=8)
def _load_domain_index(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {"domains": []}
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"domains": []}


@lru_cache(maxsize=8)
def _load_parameter_summary(path: str) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _query_sqlite(path: Path, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _like_where(terms: list[str], columns: list[str]) -> tuple[str, list[str]]:
    if not terms:
        return "", []
    clauses: list[str] = []
    params: list[str] = []
    for term in terms:
        pattern = f"%{term}%"
        term_clauses = [f"{column} like ?" for column in columns]
        clauses.append("(" + " or ".join(term_clauses) + ")")
        params.extend([pattern] * len(columns))
    return " or ".join(clauses), params


def _domain_where(domains: list[str]) -> tuple[str, list[str]]:
    domains = [domain for domain in domains if domain]
    if not domains:
        return "", []
    placeholders = ", ".join("?" for _ in domains)
    return f"domain in ({placeholders})", domains


def _score_text(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    score = 0
    for term in terms:
        if not term:
            continue
        term_lower = term.lower()
        count = lowered.count(term_lower)
        if not count:
            continue
        if len(term) >= 4:
            weight = 5
        elif len(term) == 3:
            weight = 3
        else:
            weight = 1
        score += count * weight
    return score


def _dedupe(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        if value is None:
            continue
        key = str(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result

from __future__ import annotations

import json
import os
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.knowledge_artifact import KnowledgeArtifact
from app.models.parameter_observation import ParameterObservation

router = APIRouter(tags=["dashboards"], dependencies=[Depends(get_current_user)])

_NON_BOUNDARY_ECONOMIC_TERMS = (
    "市场规模", "行业规模", "融资", "订单", "营收", "估值", "出货", "装机量", "产能",
)
_DECISION_ECONOMIC_TERMS = (
    "成本", "CAPEX", "OPEX", "价格", "电价", "LCOE", "LCOA", "LCOH", "投资回收",
)


def _is_boundary_parameter(param: ParameterObservation) -> bool:
    """Keep engineering boundaries and only decision-causal economics."""
    name = param.parameter_name or ""
    if any(term in name for term in _NON_BOUNDARY_ECONOMIC_TERMS):
        return False
    if param.parameter_type == "technical":
        return True
    if param.parameter_type == "economic":
        return any(term.lower() in name.lower() for term in _DECISION_ECONOMIC_TERMS)
    return False


def _parameter_value(param: ParameterObservation) -> str:
    if param.value_text:
        return param.value_text
    if param.value_min is not None and param.value_max is not None:
        return f"{param.value_min}-{param.value_max}" if param.value_min != param.value_max else str(param.value_min)
    if param.value_min is not None:
        return str(param.value_min)
    return "-"


def _parameter_payload(
    param: ParameterObservation,
    commercial_statuses: dict[str, str] | None = None,
    commercial_status_reasons: dict[str, str] | None = None,
) -> dict:
    commercial_statuses = commercial_statuses or {}
    commercial_status_reasons = commercial_status_reasons or {}
    return {
        "name": param.parameter_name,
        "value": _parameter_value(param),
        "unit": param.unit or "",
        "type": param.parameter_type,
        "verification": param.verification_status,
        "commercial_status": commercial_statuses.get(param.parameter_name, ""),
        "commercial_status_reason": commercial_status_reasons.get(param.parameter_name, ""),
    }

# Legacy dashboards kept for backward compatibility (until KB artifacts fully cover them)
_LEGACY_DASHBOARDS = [
    {
        "id": "sofc-soc",
        "name": "SOFC / SOC",
        "scope": "数据中心电源、分布式发电、rSOC",
        "metrics": ["电解质电导率", "堆寿命", "系统效率", "单位投资成本", "燃料利用率"],
        "status": "重点研究",
        "query": "SOFC",
        "domain": "SOFC",
    },
    {
        "id": "aidc-power",
        "name": "AIDC 能源系统",
        "scope": "供电架构、备用电源、热管理",
        "metrics": ["可用率", "PUE", "电力容量", "审批周期", "备用时长"],
        "status": "进行中",
        "query": "AIDC",
        "domain": "AIDC",
    },
]


def _build_kb_dashboards(db: Session) -> list[dict]:
    """Build dashboard cards from knowledge_artifacts + parameter_observations.

    Each deep_research_note artifact becomes a dashboard card. Key parameters
    are aggregated as metric highlights.
    """
    if not hasattr(db, "query"):
        return []

    artifacts = db.query(KnowledgeArtifact).filter(
        KnowledgeArtifact.artifact_type == "deep_research_note",
        KnowledgeArtifact.status == "active",
    ).order_by(KnowledgeArtifact.updated_at.desc()).all()

    dashboards: list[dict] = []
    for art in artifacts:
        tech_node_ids = art.related_tech_node_ids or []

        metrics: list[str] = []
        key_indicators: list[dict] = []
        params: list[ParameterObservation] = []
        if tech_node_ids:
            params = db.query(ParameterObservation).filter(
                ParameterObservation.technology_node_id.in_(tech_node_ids)
            ).all()
            params = [param for param in params if _is_boundary_parameter(param)]

        # Derive dashboard id from stable_id
        raw_sid = art.stable_id or str(art.id)[:8]
        for _prefix in ("ART-20260709-", "ART-20260712-"):
            if raw_sid.startswith(_prefix):
                raw_sid = raw_sid[len(_prefix):]
                break
        dash_id = raw_sid.lower()

        # Extract decision metadata from the KB document frontmatter.  These
        # fields let the UI distinguish reviewed reports from imported notes.
        taxonomy_leaf = ""
        decision_question = ""
        verdict = ""
        confidence = ""
        review_status = ""
        metric_review_status = ""
        homepage_indicator_names: list[str] = []
        commercial_statuses: dict[str, str] = {}
        commercial_status_reasons: dict[str, str] = {}
        featured = False
        cross_ref = ""
        try:
            import re as _re
            from pathlib import Path as _Path
            kb_base = os.getenv("TECHDB_KB_PATH", "/knowledge-base")
            for vp in [_Path(kb_base) / (art.vault_path or ""), _Path("/knowledge-base") / (art.vault_path or "")]:
                if vp.exists():
                    raw = vp.read_text(encoding="utf-8", errors="ignore")[:6000]
                    m = _re.search(r'taxonomy_leaf:\s*(.+)', raw)
                    if m:
                        taxonomy_leaf = m.group(1).strip()
                    def _fm_value(key: str) -> str:
                        match = _re.search(rf'^{key}:\s*(.+)$', raw, _re.MULTILINE)
                        return match.group(1).strip() if match else ""
                    decision_question = _fm_value("decision_question")
                    verdict = _fm_value("verdict")
                    confidence = _fm_value("confidence")
                    review_status = _fm_value("review_status")
                    metric_review_status = _fm_value("metric_review_status")
                    homepage_indicator_names = [name.strip() for name in _fm_value("homepage_indicators").split("|") if name.strip()]
                    for key, target in (
                        ("commercial_statuses", commercial_statuses),
                        ("commercial_status_reasons", commercial_status_reasons),
                    ):
                        value = _fm_value(key)
                        if value:
                            parsed = json.loads(value)
                            if isinstance(parsed, dict):
                                target.update({str(name): str(status) for name, status in parsed.items()})
                    cross_ref = _fm_value("cross_ref")
                    featured = _fm_value("featured").lower() in {"true", "yes", "1"}
                    break
        except Exception:
            pass

        # Homepage indicators are editorial decisions, not arbitrary database
        # row order. A reviewed allow-list wins; otherwise technical parameters
        # are stable and appear before economic or commercial context.
        if homepage_indicator_names:
            by_name = {param.parameter_name: param for param in params}
            selected_params = [by_name[name] for name in homepage_indicator_names if name in by_name]
        else:
            selected_params = sorted(
                params,
                key=lambda param: (
                    param.parameter_type != "technical",
                    param.parameter_type or "",
                    param.parameter_name,
                ),
            )[:6]
        for param in selected_params:
            payload = _parameter_payload(param, commercial_statuses, commercial_status_reasons)
            unit = f" {payload['unit']}" if payload["unit"] and payload["unit"] != "-" else ""
            metrics.append(f"{payload['name']}: {payload['value']}{unit}")
            key_indicators.append(payload)

        dashboards.append({
            "id": dash_id,
            "name": art.title.replace("_技术边界", "").replace("_", " "),
            "scope": _derive_scope(art),
            "metrics": metrics,
            "key_indicators": key_indicators,
            "status": "重点研究",
            "query": dash_id,
            "domain": art.title.split("_")[0] if "_" in art.title else art.title,
            "source": "knowledge_base",
            "artifact_id": str(art.id),
            "stable_id": art.stable_id,
            "vault_path": art.vault_path,
            "version": art.version,
            "updated_at": art.updated_at.isoformat() if art.updated_at else None,
            "tech_node_ids": tech_node_ids,
            "taxonomy_leaf": taxonomy_leaf,
            "cross_ref": cross_ref,
            "decision_question": decision_question,
            "verdict": verdict,
            "confidence": confidence,
            "review_status": review_status,
            "metric_review_status": metric_review_status,
            "homepage_indicators": homepage_indicator_names,
            "commercial_statuses": commercial_statuses,
            "commercial_status_reasons": commercial_status_reasons,
            "featured": featured,
        })

    dashboards.sort(key=lambda item: (not item.get("featured", False), item.get("name", "")))
    return dashboards


def _derive_scope(art: KnowledgeArtifact) -> str:
    """Extract a scope summary from the artifact title."""
    title = art.title
    # "压缩空气储能_长时储能技术边界" → "长时储能技术边界"
    if "_" in title:
        parts = title.split("_", 1)
        if len(parts) > 1:
            rest = parts[1].replace("技术边界", "").strip("_")
            return rest or "深度调研"
    return "深度调研"


@router.get("/dashboards")
def list_dashboards(
    q: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> dict:
    """List dashboard cards.

    Combines data-driven dashboards from knowledge_artifacts (deep_research_note)
    with legacy hardcoded dashboards for backward compatibility.
    """
    kb_dashboards = _build_kb_dashboards(db)
    all_items = kb_dashboards + _LEGACY_DASHBOARDS

    keyword = (q or "").strip().lower()
    if keyword:
        items = [
            item for item in all_items
            if keyword in item.get("name", "").lower()
            or keyword in item.get("scope", "").lower()
            or keyword in item.get("domain", "").lower()
            or any(keyword in m.lower() for m in item.get("metrics", []))
        ]
    else:
        items = all_items

    return {"items": items, "total": len(items)}


@router.get("/dashboards/{dashboard_id}")
def get_dashboard_detail(
    dashboard_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Get detailed dashboard data for a specific track.

    Returns all parameters + metadata for the knowledge artifact.
    """
    # Find by stable_id-derived id or legacy id
    all_dashboards = _build_kb_dashboards(db) + [
        {**d, "source": "legacy"} for d in _LEGACY_DASHBOARDS
    ]

    dashboard = next((d for d in all_dashboards if d["id"] == dashboard_id), None)
    if not dashboard:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="dashboard_not_found")

    # If KB-sourced, fetch all parameters
    detailed_indicators: list[dict] = []
    tech_node_ids = dashboard.get("tech_node_ids", [])
    if tech_node_ids:
        params = db.query(ParameterObservation).filter(
            ParameterObservation.technology_node_id.in_(tech_node_ids)
        ).all()
        for p in params:
            if not _is_boundary_parameter(p):
                continue
            val = _parameter_value(p)

            detailed_indicators.append({
                "name": p.parameter_name,
                "value": val,
                "value_min": float(p.value_min) if p.value_min is not None else None,
                "value_max": float(p.value_max) if p.value_max is not None else None,
                "value_text": p.value_text,
                "unit": p.unit or "",
                "type": p.parameter_type,
                "condition": p.condition_text or "",
                "verification": p.verification_status,
                "commercial_status": dashboard.get("commercial_statuses", {}).get(p.parameter_name, ""),
                "commercial_status_reason": dashboard.get("commercial_status_reasons", {}).get(p.parameter_name, ""),
                "notes": p.notes or "",
            })

    result = dict(dashboard)
    result["detailed_indicators"] = detailed_indicators
    return result


@router.get("/dashboards/{dashboard_id}/content")
def get_dashboard_content(
    dashboard_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Get structured industry dashboard data parsed from the KB document.

    Parses the markdown into structured JSON suitable for native frontend
    rendering (not raw markdown):
    - summary: §0 text
    - value_anchor: §0.5 convergence table
    - roadmap: §1 technology routes table
    - indicators: §2 key metrics table
    - bottlenecks: §3 bottleneck analysis
    - alerts: §7 breakout watch
    """
    import re as _re
    from pathlib import Path as _Path

    all_dashboards = _build_kb_dashboards(db)
    dashboard = next((d for d in all_dashboards if d["id"] == dashboard_id), None)
    if not dashboard:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="dashboard_not_found")

    vault_path = dashboard.get("vault_path")
    if not vault_path:
        return _empty_dashboard()

    kb_base_env = os.getenv("TECHDB_KB_PATH", "/knowledge-base")
    candidates = [
        _Path(kb_base_env) / vault_path,
        _Path("/knowledge-base") / vault_path,
    ]
    md_path = next((p for p in candidates if p.exists()), None)
    if not md_path:
        return _empty_dashboard()

    raw = md_path.read_text(encoding="utf-8", errors="ignore")

    # Split into sections (## headers), keeping ### subsections as content
    sections: dict[str, str] = {}
    current_title = ""
    current_lines: list[str] = []
    fm_count = 0  # Track frontmatter delimiters (first two --- only)

    for line in raw.split("\n"):
        if line.strip() == "---" and fm_count < 2:
            fm_count += 1
            continue
        if fm_count < 2:
            continue  # still in frontmatter

        sec_match = _re.match(r"^##\s+(.+)$", line)
        if sec_match:
            if current_title:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = sec_match.group(1).strip()
            current_lines = []
        elif current_title:
            current_lines.append(line)

    if current_title:
        sections[current_title] = "\n".join(current_lines).strip()

    # Also index ### subsections so find_section can match "§2.5" etc.
    sub_sections: dict[str, str] = {}
    for title, body in sections.items():
        sub_parts = _re.split(r'^(###\s+.+)$', body, flags=_re.MULTILINE)
        for i in range(1, len(sub_parts), 2):
            sub_header = _re.sub(r'^###\s+', '', sub_parts[i]).strip()
            sub_body = sub_parts[i + 1].strip() if i + 1 < len(sub_parts) else ""
            sub_sections[sub_header] = sub_body
    sections.update(sub_sections)

    # Helper: find section by partial key match (exact first, then partial)
    def find_section(*keywords) -> str:
        # Exact match first
        for title, content in sections.items():
            if all(kw == title for kw in keywords):
                return content
        # Partial match
        for title, content in sections.items():
            if all(kw in title for kw in keywords):
                return content
        return ""

    # Parse markdown tables into rows
    def parse_table(md: str) -> list[dict]:
        if not md:
            return []
        lines = md.strip().split("\n")
        table_lines = [l.strip() for l in lines if l.strip().startswith("|")]
        if len(table_lines) < 2:
            return []
        # First line = headers
        headers = [h.strip() for h in table_lines[0].split("|")][1:-1]
        rows = []
        for line in table_lines[2:]:  # skip separator line
            cells = [c.strip() for c in line.split("|")][1:-1]
            if len(cells) == len(headers):
                row = {}
                for i, h in enumerate(headers):
                    # Clean markdown bold/italic from cell
                    clean = _re.sub(r'\*\*(.+?)\*\*', r'\1', cells[i])
                    clean = _re.sub(r'\*(.+?)\*', r'\1', clean)
                    row[h] = clean
                rows.append(row)
        return rows

    # Extract summary (§0 定位摘要): first paragraph
    summary_raw = find_section("§0 定位摘要")
    # Remove markdown formatting, keep as clean text
    summary = _re.sub(r'^###.*$', '', summary_raw, flags=_re.MULTILINE).strip()
    summary = _re.sub(r'\*\*(.+?)\*\*', r'\1', summary)
    summary = _re.sub(r'\*(.+?)\*', r'\1', summary)
    summary = summary[:2000] if len(summary) > 2000 else summary

    # Value anchor table (§0.5 convergence)
    anchor_raw = find_section("§0.5")
    # Find the convergence table (contains 应用场景)
    anchor_rows = []
    if anchor_raw:
        # Find table after 价值锚点收敛
        conv_idx = anchor_raw.find("价值锚点收敛")
        if conv_idx >= 0:
            table_section = anchor_raw[conv_idx:]
            anchor_rows = parse_table(table_section)

    # Roadmap (§1): technology routes table
    roadmap_raw = find_section("§1")
    roadmap_rows = parse_table(roadmap_raw) if roadmap_raw else []

    # Indicators (§2): key metrics tables
    indicators_raw = find_section("§2")
    indicator_rows = parse_table(indicators_raw) if indicators_raw else []

    # Bottlenecks (§3): parse ### subsections
    bottlenecks_raw = find_section("§3")

    # §2.5 feasibility verification table
    feasibility_raw = find_section("§2.5") or find_section("物理可达性") or find_section("可达性验证")
    feasibility_rows = parse_table(feasibility_raw) if feasibility_raw else []

    bottlenecks = []
    if bottlenecks_raw:
        # Split by ### headers
        bn_parts = _re.split(r'^###\s+', bottlenecks_raw, flags=_re.MULTILINE)
        for part in bn_parts[1:]:  # skip preamble
            lines = part.strip().split("\n")
            title = lines[0].strip()
            # Extract 卡在哪里/为什么卡/谁在解/突破信号
            content = "\n".join(lines[1:])
            blockage = ""
            nature = ""
            solvers = ""
            signals = ""

            for line in lines[1:]:
                line_clean = line.strip()
                if line_clean.startswith("**卡在哪里**") or line_clean.startswith("卡在哪里"):
                    blockage = _re.sub(r'\*\*.*?\*\*[：:]\s*', '', line_clean)
                    blockage = _re.sub(r'^卡在哪里[：:]\s*', '', blockage)
                elif line_clean.startswith("**为什么卡**") or line_clean.startswith("为什么卡"):
                    nature = _re.sub(r'\*\*.*?\*\*[：:]\s*', '', line_clean)
                    nature = _re.sub(r'^为什么卡[：:]\s*', '', nature)
                elif line_clean.startswith("**谁在解**") or line_clean.startswith("谁在解"):
                    solvers = _re.sub(r'\*\*.*?\*\*[：:]\s*', '', line_clean)
                    solvers = _re.sub(r'^谁在解[：:]\s*', '', solvers)
                elif line_clean.startswith("**突破信号**") or line_clean.startswith("突破信号"):
                    signals = _re.sub(r'\*\*.*?\*\*[：:]\s*', '', line_clean)
                    signals = _re.sub(r'^突破信号[：:]\s*', '', signals)

            # Fallback: if nature is empty, look for "**物理限制**" / "**工程" / "**经济" sub-bullets
            if not nature.strip():
                nature_parts = []
                for line in lines[1:]:
                    lc = line.strip()
                    for kw in ["物理限制", "工程问题", "工程突破", "经济问题", "物理化学"]:
                        if f"**{kw}**" in lc or lc.startswith(f"- **{kw}**"):
                            # Extract text after the bold label
                            text = _re.sub(r'^-?\s*\*\*.*?\*\*[（(]?[^）)：:]*[）)：:]\s*', '', lc)
                            text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)
                            if text.strip():
                                nature_parts.append(text.strip()[:150])
                            break
                # Also check for "> **限制性质**" blockquote summary
                for line in lines[1:]:
                    lc = line.strip()
                    if lc.startswith("> **限制性质**") or lc.startswith(">**限制性质**"):
                        text = _re.sub(r'^>\s*\*\*限制性质\*\*[：:]\s*', '', lc)
                        text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)
                        if text.strip() and not nature_parts:
                            nature_parts.append(text.strip()[:200])
                        break
                if nature_parts:
                    nature = "；".join(nature_parts)

            bottlenecks.append({
                "title": title,
                "blockage": blockage.strip(),
                "nature": nature.strip(),
                "solvers": solvers.strip(),
                "signals": signals.strip(),
            })

    # Alerts (§7): breakout watch table
    alerts_raw = find_section("§7") or find_section("预警")
    alert_rows = parse_table(alerts_raw) if alerts_raw else []

    # §4: Common technology analysis — extract bullets, bold paragraphs, or table rows
    common_raw = find_section("§4")
    common_items: list[str] = []
    if common_raw:
        # Try bullet points first
        for line in common_raw.splitlines():
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                item = _re.sub(r'^[-•]\s*', '', line)
                item = _re.sub(r'\*\*(.+?)\*\*', r'\1', item)
                common_items.append(item.strip())
        # If no bullets, try bold paragraphs: "**与XX的交叉**：..."
        if not common_items:
            for m in _re.finditer(r'\*\*(.+?)\*\*[：:](.+?)(?=\n\*\*|\n\n|\Z)', common_raw, _re.S):
                title_part = m.group(1).strip()
                body_part = m.group(2).strip().replace('\n', ' ')
                body_part = _re.sub(r'\*\*(.+?)\*\*', r'\1', body_part)
                common_items.append(f"{title_part}：{body_part[:200]}")
        # If still nothing, try table format
        if not common_items:
            common_rows = parse_table(common_raw)
            for row in common_rows:
                parts = [str(row.get(k, "")).strip() for k in row]
                item = " | ".join(p for p in parts if p)
                if item.strip():
                    common_items.append(item)

    # §6: To-verify checklist — extract bullet points or table rows
    verify_raw = find_section("§6")
    verify_items: list[str] = []
    if verify_raw:
        # Try bullet points first
        for line in verify_raw.splitlines():
            line = line.strip()
            if line.startswith("- ") or line.startswith("• "):
                item = _re.sub(r'^[-•]\s*', '', line)
                item = _re.sub(r'\*\*(.+?)\*\*', r'\1', item)
                verify_items.append(item.strip())
        # If no bullets found, try table format
        if not verify_items:
            verify_rows = parse_table(verify_raw)
            for row in verify_rows:
                parts = [str(row.get(k, "")).strip() for k in row]
                item = " | ".join(p for p in parts if p)
                if item.strip():
                    verify_items.append(item)

    # Build raw_sections: full markdown text for each ## section
    raw_sections: dict[str, str] = {}
    for title, body in sections.items():
        # Skip ### subsections (they're included in their parent ## section)
        if title in sub_sections:
            continue
        raw_sections[title] = body

    return {
        "dashboard_id": dashboard_id,
        "name": dashboard.get("name", ""),
        "scope": dashboard.get("scope", ""),
        "vault_path": vault_path,
        "taxonomy_leaf": dashboard.get("taxonomy_leaf", ""),
        "cross_ref": dashboard.get("cross_ref", ""),
        "decision_question": dashboard.get("decision_question", ""),
        "verdict": dashboard.get("verdict", ""),
        "confidence": dashboard.get("confidence", ""),
        "review_status": dashboard.get("review_status", ""),
        "featured": dashboard.get("featured", False),
        "summary": summary,
        "value_anchor": anchor_rows,
        "roadmap": roadmap_rows,
        "indicators": indicator_rows,
        "feasibility": feasibility_rows,
        "bottlenecks": bottlenecks,
        "common_tech": common_items,
        "to_verify": verify_items,
        "alerts": alert_rows,
        "raw_sections": raw_sections,
    }


def _empty_dashboard() -> dict:
    return {
        "summary": "",
        "value_anchor": [],
        "roadmap": [],
        "indicators": [],
        "feasibility": [],
        "bottlenecks": [],
        "common_tech": [],
        "to_verify": [],
        "alerts": [],
    }

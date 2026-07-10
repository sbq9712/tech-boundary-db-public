from __future__ import annotations

import os
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.knowledge_artifact import KnowledgeArtifact
from app.models.parameter_observation import ParameterObservation

router = APIRouter(tags=["dashboards"], dependencies=[Depends(get_current_user)])

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
    artifacts = db.query(KnowledgeArtifact).filter(
        KnowledgeArtifact.artifact_type == "deep_research_note",
        KnowledgeArtifact.status == "active",
    ).order_by(KnowledgeArtifact.updated_at.desc()).all()

    dashboards: list[dict] = []
    for art in artifacts:
        tech_node_ids = art.related_tech_node_ids or []

        # Pull key parameters for this artifact's tech nodes
        params_q = db.query(ParameterObservation).filter(
            ParameterObservation.technology_node_id.in_(tech_node_ids)
        ) if tech_node_ids else []

        metrics: list[str] = []
        key_indicators: list[dict] = []
        if tech_node_ids:
            params = db.query(ParameterObservation).filter(
                ParameterObservation.technology_node_id.in_(tech_node_ids)
            ).limit(6).all()
            for p in params:
                # Build display value
                if p.value_text:
                    val = p.value_text
                elif p.value_min is not None and p.value_max is not None:
                    val = f"{p.value_min}–{p.value_max}" if p.value_min != p.value_max else str(p.value_min)
                elif p.value_min is not None:
                    val = str(p.value_min)
                else:
                    val = "—"

                unit = f" {p.unit}" if p.unit and p.unit != "—" else ""
                metrics.append(f"{p.parameter_name}: {val}{unit}")
                key_indicators.append({
                    "name": p.parameter_name,
                    "value": val,
                    "unit": p.unit or "",
                    "type": p.parameter_type,
                    "verification": p.verification_status,
                })

        # Derive dashboard id from stable_id
        dash_id = art.stable_id.replace("ART-20260709-", "").lower() if art.stable_id else str(art.id)[:8]

        # Extract taxonomy_leaf from the KB document frontmatter
        taxonomy_leaf = ""
        try:
            import re as _re
            from pathlib import Path as _Path
            kb_base = os.getenv("TECHDB_KB_PATH", "/knowledge-base")
            for vp in [_Path(kb_base) / (art.vault_path or ""), _Path("/knowledge-base") / (art.vault_path or "")]:
                if vp.exists():
                    raw = vp.read_text(encoding="utf-8", errors="ignore")[:2000]
                    m = _re.search(r'taxonomy_leaf:\s*(.+)', raw)
                    if m:
                        taxonomy_leaf = m.group(1).strip()
                    break
        except Exception:
            pass

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
        })

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
            if p.value_text:
                val = p.value_text
            elif p.value_min is not None and p.value_max is not None:
                val = f"{p.value_min}–{p.value_max}" if p.value_min != p.value_max else str(p.value_min)
            elif p.value_min is not None:
                val = str(p.value_min)
            else:
                val = "—"

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

    # Split into sections
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
    summary = summary[:600] if len(summary) > 600 else summary

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

    return {
        "dashboard_id": dashboard_id,
        "name": dashboard.get("name", ""),
        "scope": dashboard.get("scope", ""),
        "vault_path": vault_path,
        "summary": summary,
        "value_anchor": anchor_rows,
        "roadmap": roadmap_rows,
        "indicators": indicator_rows,
        "bottlenecks": bottlenecks,
        "alerts": alert_rows,
    }


def _empty_dashboard() -> dict:
    return {
        "summary": "",
        "value_anchor": [],
        "roadmap": [],
        "indicators": [],
        "bottlenecks": [],
        "alerts": [],
    }

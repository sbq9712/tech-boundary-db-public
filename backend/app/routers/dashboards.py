from __future__ import annotations

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

from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.parameter_observation import ParameterObservation

router = APIRouter(tags=["parameter-observations"], dependencies=[Depends(get_current_user)])


class ParamObsIn(BaseModel):
    intelligence_id: UUID | None = None
    source_id: UUID | None = None
    evidence_id: UUID | None = None
    technology_node_id: str | None = None
    parameter_name: str
    parameter_type: str = "technical"
    value_min: float | None = None
    value_max: float | None = None
    value_text: str | None = None
    unit: str | None = None
    condition_text: str | None = None
    scenario: str | None = None
    actor_or_company: str | None = None
    extraction_confidence: str = "medium"
    verification_status: str = "machine_extracted"
    notes: str | None = None


def _obs_dict(obs: ParameterObservation) -> dict:
    return {
        "id": str(obs.id),
        "stable_id": obs.stable_id,
        "intelligence_id": str(obs.intelligence_id) if obs.intelligence_id else None,
        "source_id": str(obs.source_id) if obs.source_id else None,
        "technology_node_id": obs.technology_node_id,
        "parameter_name": obs.parameter_name,
        "parameter_type": obs.parameter_type,
        "value_min": float(obs.value_min) if obs.value_min is not None else None,
        "value_max": float(obs.value_max) if obs.value_max is not None else None,
        "value_text": obs.value_text,
        "unit": obs.unit,
        "condition_text": obs.condition_text,
        "scenario": obs.scenario,
        "actor_or_company": obs.actor_or_company,
        "extraction_confidence": obs.extraction_confidence,
        "verification_status": obs.verification_status,
        "created_at": obs.created_at.isoformat(),
    }


@router.get("/parameter-observations")
def list_parameter_observations(
    intelligence_id: UUID | None = None,
    technology_node_id: str | None = None,
    parameter_name: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(ParameterObservation)
    if intelligence_id:
        stmt = stmt.where(ParameterObservation.intelligence_id == intelligence_id)
    if technology_node_id:
        stmt = stmt.where(ParameterObservation.technology_node_id == technology_node_id)
    if parameter_name:
        stmt = stmt.where(ParameterObservation.parameter_name.ilike(f"%{parameter_name}%"))
    stmt = stmt.order_by(ParameterObservation.created_at.desc()).limit(limit)
    items = db.scalars(stmt).all()
    return {"total": len(items), "items": [_obs_dict(o) for o in items]}


@router.post("/parameter-observations", status_code=201)
def create_parameter_observation(
    payload: ParamObsIn,
    db: Session = Depends(get_db),
) -> dict:
    obs = ParameterObservation(
        id=uuid.uuid4(),
        **payload.model_dump(),
    )
    db.add(obs)
    db.commit()
    db.refresh(obs)
    return _obs_dict(obs)


@router.patch("/parameter-observations/{obs_id}/verify")
def verify_observation(
    obs_id: UUID,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> dict:
    obs = db.get(ParameterObservation, obs_id)
    if not obs:
        raise HTTPException(404, "observation not found")
    obs.verification_status = "human_checked"
    db.commit()
    db.refresh(obs)
    return _obs_dict(obs)

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.domain import Domain
from app.models.info_item import InfoItem, InfoItemDomain
from app.schemas import (
    AlertUpsertIn,
    IndicatorsUpsertIn,
    InfoItemDetailsUpdateIn,
    InfoItemDraftIn,
    InfoItemOut,
    InfoItemPublishIn,
)
from app.services.data_loader import load_json

router = APIRouter(tags=["info-items"], dependencies=[Depends(get_current_user)])


DRAFT_STATUSES = {"draft", "ai_suggested"}
_INDICATOR_DEFS_CACHE: list[dict] | None = None
_DOMAINS_CACHE: list[dict] | None = None


def _normalize_indicator_name(name: str | None) -> str:
    return (
        str(name or "")
        .replace("CO₂", "CO2")
        .replace("(", "")
        .replace(")", "")
        .replace("（", "")
        .replace("）", "")
        .replace("[", "")
        .replace("]", "")
        .replace("【", "")
        .replace("】", "")
        .replace(" ", "")
        .replace("\t", "")
        .replace("\n", "")
        .lower()
    )


def _get_indicator_defs() -> list[dict]:
    global _INDICATOR_DEFS_CACHE
    if _INDICATOR_DEFS_CACHE is None:
        raw = load_json("indicator_defs.json")
        _INDICATOR_DEFS_CACHE = [
            row for row in raw
            if isinstance(row, dict) and row.get("is_active", True) and row.get("name") and row.get("id")
        ]
    return _INDICATOR_DEFS_CACHE


def _get_domains() -> list[dict]:
    global _DOMAINS_CACHE
    if _DOMAINS_CACHE is None:
        raw = load_json("domains.json")
        _DOMAINS_CACHE = [row for row in raw if isinstance(row, dict) and row.get("id")]
    return _DOMAINS_CACHE


def _get_ccus_level2_domain_ids(domain_ids: list[str] | None) -> set[str]:
    if not domain_ids:
        return set()

    domain_by_id = {str(row["id"]): row for row in _get_domains()}
    matched_ids: set[str] = set()

    for domain_id in domain_ids:
        current = domain_by_id.get(str(domain_id))
        visited: set[str] = set()
        while current:
            current_id = str(current.get("id") or "")
            if current_id in visited:
                break
            visited.add(current_id)
            if current_id.startswith("DOM_CCUS_L2_"):
                matched_ids.add(current_id)
                break
            parent_id = str(current.get("parent_id") or "").strip()
            current = domain_by_id.get(parent_id) if parent_id else None

    return matched_ids


def _normalize_draft_data(draft_data: dict | None, domain_ids: list[str] | None = None) -> dict:
    normalized = dict(draft_data or {})
    raw_indicators = normalized.get("indicators")
    if not isinstance(raw_indicators, list):
        return normalized

    defs = _get_indicator_defs()
    by_id = {str(row["id"]): row for row in defs}
    by_name: dict[str, dict] = {}
    for row in defs:
        keys = [
            _normalize_indicator_name(row.get("name")),
            _normalize_indicator_name(row.get("match_name")),
        ]
        for key in keys:
            if key and key not in by_name:
                by_name[key] = row

    allowed_ccus_level2_ids = _get_ccus_level2_domain_ids(domain_ids)

    fixed_indicators: list[dict] = []
    for row in raw_indicators:
        if not isinstance(row, dict):
            continue
        indicator_id = str(row.get("indicator_id") or "").strip()
        name = str(row.get("name") or "").strip()
        unit = str(row.get("unit") or "").strip()
        matched = by_id.get(indicator_id) or by_name.get(_normalize_indicator_name(name))
        if not matched:
            continue
        allowed_domain_ids = {
            str(value)
            for value in (matched.get("allowed_domain_ids") or [])
            if str(value).strip()
        }
        if allowed_ccus_level2_ids and allowed_domain_ids and not (allowed_domain_ids & allowed_ccus_level2_ids):
            continue

        fixed_indicators.append({
            "indicator_id": matched["id"],
            "name": matched["name"],
            "value": row.get("value", ""),
            "unit": unit or matched.get("unit_default", ""),
            "keep": row.get("keep", True),
        })

    normalized["indicators"] = fixed_indicators
    return normalized


def _to_info_item_out(item: InfoItem) -> InfoItemOut:
    return InfoItemOut(
        id=item.id,
        title=item.title,
        content=item.content,
        source_url=item.source_url,
        published_at=item.published_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        status=item.status,
        importance_score=item.importance_score,
        is_new_tech=item.is_new_tech,
        comment=item.comment,
        source_types=item.source_types or [],
        info_types=item.info_types or [],
        tags=item.tags or [],
        domain_ids=[rel.domain_id for rel in item.domains],
        classification=item.classification,
        draft_data=item.draft_data or {},
        alert_status=item.alert_status,
        alert_source=item.alert_source,
        alert_manual_override=item.alert_manual_override,
        alert_title=item.alert_title,
        alert_body=item.alert_body,
        alert_reviewer_comment=item.alert_reviewer_comment,
        alert_dismiss_reason=item.alert_dismiss_reason,
        alert_color=item.alert_color,
        alert_created_at=item.alert_created_at,
        alert_expires_at=item.alert_expires_at,
        last_modified_by=item.last_modified_by,
        created_by=item.created_by,
    )


def _apply_alert_payload(item: InfoItem, alert: AlertUpsertIn | None) -> None:
    if not alert or not alert.enabled:
        item.alert_status = "dismissed" if alert else None
        item.alert_source = "manual" if alert else None
        item.alert_manual_override = bool(alert)
        item.alert_title = None
        item.alert_body = None
        item.alert_reviewer_comment = None
        item.alert_color = None
        item.alert_created_at = None
        item.alert_expires_at = None
        item.alert_dismiss_reason = alert.dismiss_reason if alert else None
        return

    if not alert.alert_title:
        raise HTTPException(status_code=400, detail="alert_title is required when alert is enabled")
    if not alert.alert_body:
        raise HTTPException(status_code=400, detail="alert_body is required when alert is enabled")
    if not alert.reviewer_comment:
        raise HTTPException(status_code=400, detail="reviewer_comment is required when alert is enabled")
    if alert.expires_at:
        expires_at = alert.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="expires_at must be in the future")

    item.alert_status = "active"
    if item.alert_created_at is None:
        item.alert_created_at = datetime.now(timezone.utc)
    item.alert_source = "manual"
    item.alert_manual_override = True
    item.alert_title = alert.alert_title
    item.alert_body = alert.alert_body
    item.alert_reviewer_comment = alert.reviewer_comment
    item.alert_color = alert.alert_color or "orange"
    item.alert_expires_at = alert.expires_at
    item.alert_dismiss_reason = None


def _validate_domain_ids(db: Session, domain_ids: list[str]) -> list[str]:
    if not domain_ids:
        raise HTTPException(status_code=400, detail="domain_ids is required")
    unique_ids = list(dict.fromkeys(domain_ids))
    existing_domain_ids = set(
        db.scalars(select(Domain.id).where(Domain.id.in_(unique_ids))).all()
    )
    if len(existing_domain_ids) != len(unique_ids):
        raise HTTPException(status_code=400, detail="some domain_ids do not exist")

    domain_meta_by_id = {str(row["id"]): row for row in _get_domains()}
    invalid_level_ids = [
        domain_id
        for domain_id in unique_ids
        if int(domain_meta_by_id.get(domain_id, {}).get("level") or 0) != 4
    ]
    if invalid_level_ids:
        raise HTTPException(
            status_code=400,
            detail=f"domain_ids must all be level-4 leaf domains: {', '.join(invalid_level_ids)}",
        )
    return unique_ids


def _replace_domains(db: Session, item: InfoItem, domain_ids: list[str]) -> None:
    existing_relations = db.scalars(
        select(InfoItemDomain).where(InfoItemDomain.info_item_id == item.id)
    ).all()

    desired_ids = set(domain_ids)
    existing_by_id = {rel.domain_id: rel for rel in existing_relations}

    for rel in existing_relations:
        if rel.domain_id not in desired_ids:
            db.delete(rel)

    for idx, domain_id in enumerate(domain_ids):
        rel = existing_by_id.get(domain_id)
        if rel:
            rel.is_primary = idx == 0
        else:
            db.add(InfoItemDomain(
                info_item_id=item.id,
                domain_id=domain_id,
                is_primary=(idx == 0),
            ))


def _apply_upsert_fields(item: InfoItem, payload: InfoItemDraftIn | InfoItemPublishIn) -> None:
    item.title = payload.title
    item.content = payload.content
    item.source_url = payload.source_url
    item.published_at = payload.published_at
    item.importance_score = payload.importance_score
    item.is_new_tech = payload.is_new_tech
    item.comment = payload.comment
    item.source_types = payload.source_types
    item.info_types = payload.info_types
    item.tags = payload.tags
    item.classification = payload.classification


@router.get("/info-items/alerts")
def get_active_alerts(
    db: Session = Depends(get_db),
) -> dict:
    """Return info_items with active alerts for the home portal panel."""
    stmt = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.alert_status == "active")
        .order_by(InfoItem.alert_expires_at.desc().nullslast(), InfoItem.updated_at.desc())
        .limit(30)
    )
    items = db.scalars(stmt).all()
    domain_name_by_id = {
        str(row["id"]): str(row.get("name") or "")
        for row in _get_domains()
    }
    return {
        "total": len(items),
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "alert_title": item.alert_title or item.title,
                "alert_body": item.alert_body or "",
                "alert_color": item.alert_color or "normal",
                "published_at": item.published_at.isoformat() if item.published_at else "",
                "alert_created_at": (item.alert_created_at or item.updated_at).isoformat() if (item.alert_created_at or item.updated_at) else "",
                "alert_time": (item.alert_created_at or item.updated_at).isoformat() if (item.alert_created_at or item.updated_at) else "",
                "domain_name": next(
                    (
                        domain_name_by_id.get(str(relation.domain_id), "")
                        for relation in item.domains
                        if domain_name_by_id.get(str(relation.domain_id), "")
                    ),
                    "待归类",
                ),
                "is_new_tech": item.is_new_tech,
                "reviewer_comment": item.alert_reviewer_comment or "",
                "target_url": "#breadth",
            }
            for item in items
        ],
    }


@router.get("/info-items", response_model=list[InfoItemOut])
def get_info_items(
    status_filter: str = Query("published", alias="status"),
    db: Session = Depends(get_db),
) -> list[InfoItemOut]:
    statuses = [s.strip() for s in status_filter.split(",") if s.strip()]
    if not statuses:
        statuses = ["published"]

    stmt: Select[tuple[InfoItem]] = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.status.in_(statuses))
        .order_by(InfoItem.published_at.desc().nullslast(), InfoItem.created_at.desc())
    )

    items = db.scalars(stmt).all()
    return [_to_info_item_out(item) for item in items]


@router.get("/info-items/drafts", response_model=list[InfoItemOut])
def get_drafts(db: Session = Depends(get_db)) -> list[InfoItemOut]:
    stmt: Select[tuple[InfoItem]] = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.status.in_(DRAFT_STATUSES))
        .order_by(InfoItem.updated_at.desc())
    )
    items = db.scalars(stmt).all()
    return [_to_info_item_out(item) for item in items]


@router.get("/info-items/{item_id}", response_model=InfoItemOut)
def get_info_item(item_id: UUID, db: Session = Depends(get_db)) -> InfoItemOut:
    stmt: Select[tuple[InfoItem]] = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.id == item_id)
    )
    item = db.scalars(stmt).first()
    if not item:
        raise HTTPException(status_code=404, detail="info item not found")
    return _to_info_item_out(item)


@router.get("/info-items/{item_id}/draft", response_model=InfoItemOut)
def get_draft(item_id: UUID, db: Session = Depends(get_db)) -> InfoItemOut:
    stmt: Select[tuple[InfoItem]] = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.id == item_id)
    )
    item = db.scalars(stmt).first()
    if not item or item.status not in DRAFT_STATUSES:
        raise HTTPException(status_code=404, detail="draft not found")
    return _to_info_item_out(item)


@router.delete("/info-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_info_item(item_id: UUID, db: Session = Depends(get_db)) -> Response:
    item = db.get(InfoItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="info item not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/info-items/draft", response_model=InfoItemOut, status_code=status.HTTP_201_CREATED)
def create_draft(
    payload: InfoItemDraftIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> InfoItemOut:
    if payload.status not in DRAFT_STATUSES:
        raise HTTPException(status_code=400, detail="draft status must be draft or ai_suggested")
    domain_ids = _validate_domain_ids(db, payload.domain_ids)

    item = InfoItem(status=payload.status)
    _apply_upsert_fields(item, payload)
    item.draft_data = _normalize_draft_data(payload.draft_data, domain_ids)
    item.created_by = current_user
    item.last_modified_by = current_user
    _apply_alert_payload(item, payload.alert)

    db.add(item)
    db.flush()
    _replace_domains(db, item, domain_ids)
    db.commit()
    db.refresh(item)
    return _to_info_item_out(item)


@router.put("/info-items/{item_id}/draft", response_model=InfoItemOut)
def update_draft(
    item_id: UUID,
    payload: InfoItemDraftIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> InfoItemOut:
    if payload.status not in DRAFT_STATUSES:
        raise HTTPException(status_code=400, detail="draft status must be draft or ai_suggested")
    stmt: Select[tuple[InfoItem]] = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.id == item_id)
    )
    item = db.scalars(stmt).first()
    if not item or item.status not in DRAFT_STATUSES:
        raise HTTPException(status_code=404, detail="draft not found")

    domain_ids = _validate_domain_ids(db, payload.domain_ids)
    _apply_upsert_fields(item, payload)
    item.status = payload.status
    item.draft_data = _normalize_draft_data(payload.draft_data, domain_ids)
    item.last_modified_by = current_user
    _apply_alert_payload(item, payload.alert)
    _replace_domains(db, item, domain_ids)

    db.commit()
    db.refresh(item)
    return _to_info_item_out(item)


@router.post(
    "/info-items/publish",
    response_model=InfoItemOut,
    status_code=status.HTTP_201_CREATED,
)
def publish_info_item(
    payload: InfoItemPublishIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> InfoItemOut:
    domain_ids = _validate_domain_ids(db, payload.domain_ids)

    item: InfoItem | None = None
    if payload.draft_id:
        stmt: Select[tuple[InfoItem]] = (
            select(InfoItem)
            .options(selectinload(InfoItem.domains))
            .where(InfoItem.id == payload.draft_id)
        )
        item = db.scalars(stmt).first()
        if not item or item.status not in DRAFT_STATUSES:
            raise HTTPException(status_code=404, detail="draft not found")

    is_new_item = item is None
    if is_new_item:
        item = InfoItem(status="published")
        db.add(item)

    _apply_upsert_fields(item, payload)
    # For non-draft publish, required fields must be assigned before first flush/insert.
    if payload.draft_id is None:
        db.flush()
    if is_new_item:
        item.created_by = current_user
    item.status = "published"
    if payload.draft_data:
        item.draft_data = _normalize_draft_data(payload.draft_data, domain_ids)
    elif payload.draft_id:
        item.draft_data = _normalize_draft_data(item.draft_data, domain_ids)
    else:
        item.draft_data = {}
    item.last_modified_by = current_user
    _apply_alert_payload(item, payload.alert)
    _replace_domains(db, item, domain_ids)

    # Auto-delete original published item when publishing a revision
    if payload.revision_of:
        original = db.get(InfoItem, payload.revision_of)
        if original and original.status == "published":
            # Only allow deletion if current user created or last modified the original,
            # or if neither field is set (legacy data without ownership info).
            owner_known = original.created_by or original.last_modified_by
            if owner_known and current_user not in (original.created_by, original.last_modified_by):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="无权替换该已发布情报：revision_of 关联的记录不属于当前用户",
                )
            db.delete(original)

    db.commit()
    db.refresh(item)

    return _to_info_item_out(item)


@router.patch("/info-items/{item_id}/indicators", response_model=InfoItemOut)
def upsert_indicators(
    item_id: UUID,
    payload: IndicatorsUpsertIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> InfoItemOut:
    stmt: Select[tuple[InfoItem]] = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.id == item_id)
    )
    item = db.scalars(stmt).first()
    if not item:
        raise HTTPException(status_code=404, detail="info item not found")

    domain_ids = [rel.domain_id for rel in item.domains]
    new_draft = dict(item.draft_data or {})
    new_draft["indicators"] = payload.indicators
    item.draft_data = _normalize_draft_data(new_draft, domain_ids)
    item.last_modified_by = current_user

    db.commit()
    db.refresh(item)
    return _to_info_item_out(item)


@router.patch("/info-items/{item_id}/details", response_model=InfoItemOut)
def update_info_item_details(
    item_id: UUID,
    payload: InfoItemDetailsUpdateIn,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user),
) -> InfoItemOut:
    stmt: Select[tuple[InfoItem]] = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.id == item_id)
    )
    item = db.scalars(stmt).first()
    if not item:
        raise HTTPException(status_code=404, detail="info item not found")

    item.source_url = payload.source_url
    item.source_types = payload.source_types
    item.info_types = payload.info_types
    item.tags = payload.tags
    item.comment = payload.comment
    item.classification = payload.classification
    item.last_modified_by = current_user

    db.commit()
    db.refresh(item)
    return _to_info_item_out(item)


@router.patch("/info-items/{item_id}/alert", response_model=InfoItemOut)
def upsert_info_item_alert(
    item_id: UUID,
    payload: AlertUpsertIn,
    db: Session = Depends(get_db),
) -> InfoItemOut:
    stmt: Select[tuple[InfoItem]] = (
        select(InfoItem)
        .options(selectinload(InfoItem.domains))
        .where(InfoItem.id == item_id)
    )
    item = db.scalars(stmt).first()
    if not item:
        raise HTTPException(status_code=404, detail="info item not found")

    _apply_alert_payload(item, payload)
    db.commit()
    db.refresh(item)
    return _to_info_item_out(item)

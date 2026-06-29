from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IndicatorsUpsertIn(BaseModel):
    indicators: list[dict[str, Any]] = Field(default_factory=list)


class InfoItemDetailsUpdateIn(BaseModel):
    source_url: str | None = None
    source_types: list[str] = Field(default_factory=list)
    info_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    comment: str | None = None
    classification: str | None = None


class AlertUpsertIn(BaseModel):
    enabled: bool = False
    alert_title: str | None = None
    alert_body: str | None = None
    reviewer_comment: str | None = None
    alert_color: str | None = None
    expires_at: datetime | None = None
    dismiss_reason: str | None = None


class InfoItemDraftIn(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_url: str | None = None
    published_at: datetime | None = None
    importance_score: int = Field(ge=1, le=5)
    is_new_tech: bool = False
    comment: str | None = None
    source_types: list[str] = Field(default_factory=list)
    info_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    domain_ids: list[str] = Field(min_length=1)
    classification: str | None = None
    status: str = "draft"
    draft_data: dict[str, Any] = Field(default_factory=dict)
    alert: AlertUpsertIn | None = None


class InfoItemPublishIn(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_url: str | None = None
    published_at: datetime | None = None
    importance_score: int = Field(ge=1, le=5)
    is_new_tech: bool = False
    comment: str | None = None
    source_types: list[str] = Field(default_factory=list)
    info_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    domain_ids: list[str] = Field(min_length=1)
    classification: str | None = None
    draft_id: UUID | None = None
    revision_of: UUID | None = None
    draft_data: dict[str, Any] = Field(default_factory=dict)
    alert: AlertUpsertIn | None = None


class InfoItemOut(BaseModel):
    id: UUID
    title: str
    content: str
    source_url: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    status: str
    importance_score: int
    is_new_tech: bool
    comment: str | None
    source_types: list[str]
    info_types: list[str]
    tags: list[str]
    domain_ids: list[str]
    classification: str | None
    draft_data: dict[str, Any]
    alert_status: str | None
    alert_source: str | None
    alert_manual_override: bool
    alert_title: str | None
    alert_body: str | None
    alert_reviewer_comment: str | None
    alert_dismiss_reason: str | None
    alert_color: str | None
    alert_expires_at: datetime | None
    last_modified_by: str | None
    created_by: str | None

    model_config = {"from_attributes": True}

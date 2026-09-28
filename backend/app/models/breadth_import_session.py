from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BreadthImportSession(Base):
    """GitHub 广度情报增量包导入会话（一包一会话）。

    - 与 uploaded_files 一对一（一个 zip = 一次上传 = 一个会话）；
    - checksum_sha256 幂等：同一包重复提交直接回放本会话计数，不再解包；
    - 各类计数逐项透出（契约 §4：skipped 不允许归并进 imported）。
    """

    __tablename__ = "breadth_import_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    package_date: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    data_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_upstream_conflict: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    package_deduplicated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    replayed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_titles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # v2 变化包扩展计数：{added, updated, deleted, skipped_stale,
    # skipped_unchanged, deleted_missing, gap_days}（旧字段语义不变）
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

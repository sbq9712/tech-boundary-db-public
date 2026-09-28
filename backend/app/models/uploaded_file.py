from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UploadedFile(Base):
    """管理员上传的资料文件（万用入口的落地记录）。

    新文件以 objects/<prefix>/{uuid}.{ext} 落在上传持久目录（不进 nginx 静态根），
    元数据进库。所有登录用户可下载，上传仅 admin。
    """

    __tablename__ = "uploaded_files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 相对上传根目录的存储键。旧记录为根目录文件名，新记录位于 objects/。
    stored_filename: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    # 浏览器/客户端给的原始文件名，下载时还原

    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    storage_status: Mapped[str] = mapped_column(String(20), nullable=False, default="stored")

    # 元数据：管理员可手填，文本类文件可由 AI 填充
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v7（0023）：密级（confidentiality）与来源类型（source_type）已随迁移移除；
    # 不再作为资料库业务字段存在。
    # 旧版自由文本领域标签，仅为历史兼容保留；新上传使用版本化分类字段。
    domain_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 资料日期（上传时管理员填写，可手输或日历选择）；
    # 会以【资料日期：…】前缀写进每个分块文本，并随 chunk 元数据入索引。
    document_date: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # v7（0024）资料库三分区：广度追踪 / 行业追踪 / ATSC内部报告；
    # 广度追踪再分 GitHub广度情报(github) 与 其他广度情报(other)。
    primary_section: Mapped[str] = mapped_column(String(20), nullable=False, default="industry", index=True)
    breadth_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 行业追踪/ATSC 上传时勾选"同步上传到广度情报"（默认否）：选是后在广度
    # 追踪保留一条指向本资料的记录并随资料生命周期一致（更新/删除/重试）。
    sync_breadth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # AI 填充状态，便于排查：manual | ai_filled | ai_failed | filename_fallback
    title_source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")

    taxonomy_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    primary_category: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    secondary_categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    classification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="legacy_unclassified", index=True
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Immutable derivative bundle and checksums; original stays in stored_filename.
    document_assets: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # 增量 embedding 与 QA 索引状态；分类完成不代表已经可检索。
    embedding_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submitted_by: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


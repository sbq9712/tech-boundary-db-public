from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BreadthManualRecord(Base):
    """广度情报的真实持久层（其他广度情报 1 文件 1 记录 + GitHub 增量包 1 包 N 记录）。

    - 「其他广度情报」上传：一个文件一条记录（写入路径自行保证 1:1）；
    - 「GitHub广度情报」增量包：一个 zip 包导入 N 条（upload_id 仅普通索引）；
    - 上传删除时随 FK 级联删除；读取层把本表合并进广度总表（read-only
      上游分片之上），等级沿用人工等级包含关系：lv>=1 精选 ⊇ lv>=2 重点 ⊇
      lv>=3 预警；
    - content_hash 用于幂等：同一文件/同一条记录重复处理不会重复入表。
    """

    __tablename__ = "breadth_manual_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 人工情报等级：0 不设置 / 1 精选 / 2 重点 / 3 预警（包含关系）
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # news | literature
    intelligence_type: Mapped[str] = mapped_column(String(20), nullable=False, default="news")
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    key_parameters: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 管线评分（GitHub 增量包携带）：sc 为字符串如 "7.8"；scd 为五维 dict
    score: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # ── feed-pkg/v2 增量契约字段 ──────────────────────────────────────────
    # tag/topic/ai_picked：包内 AI 精选链路字段（tg/tp/aip），此前被丢弃导致
    # 导入丢字段；source_version 为该键在 feed 侧的单调版本（旧不覆新）。
    tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_picked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 稳定 ID（sha256(t|d|u)[:16]）与 feed 规范键摘要（md5("t|d|u")hex）：
    # UPDATE/DELETE 按 feed_key_digest 直接定位既有行，避免从行字段反推键。
    stable_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    feed_key_digest: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # 逐行表格导入的溯源（原文件/工作表/行号）；整包导入为空。
    source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # feed-pkg/v2 白名单记录全量 JSON：包往返不丢字段（cl/cp/cln/dp/hb/wr
    # 等无列字段随 JSON 保留，读取层优先透出），UPDATE 时整体替换。
    record_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

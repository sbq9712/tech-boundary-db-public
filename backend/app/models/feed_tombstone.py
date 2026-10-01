"""GitHub feed 删除墓碑（持久化删除版本，防陈旧包复活记录）。

feed-pkg/v2 契约缺陷的兜底（2026-09-30，集成修复二.4）：
应用 DELETE v 后，若更晚到达的包重放该键的 ADD/UPDATE v' < v
（包乱序/补投递很常见——daily 包按日期独立生成），按行级
source_version 的"旧不覆新"判定无法生效——行已删除，无版本可比较，
记录会被静默复活。墓碑持久化「该键已删除到的版本」，导入侧据此拒绝
陈旧重放：

- v < deleted_version      → 拒绝（skipped_tombstoned）
- v == deleted_version 且内容与删除时一致 → 幂等跳过（skipped_tombstoned）
- v == deleted_version 且内容不同 → 协议冲突（conflicts，不落地）
- v > deleted_version      → 合法重新上架：清除墓碑，正常入库
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FeedTombstone(Base):
    __tablename__ = "breadth_feed_tombstones"

    # feed 规范键的 md5 hex（与 breadth_manual_records.feed_key_digest 同源）
    feed_key_digest: Mapped[str] = mapped_column(String(32), primary_key=True)
    # 删除生效时的 per-key 单调版本
    deleted_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # 删除时的内容哈希（同版本不同内容 → 冲突判定依据）；历史行无哈希时为 NULL
    deleted_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 溯源：删除来自哪次上传的包
    upload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    deleted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

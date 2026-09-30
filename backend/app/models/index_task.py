"""广度情报问答索引任务（持久队列）。

导入链路（GitHub 增量包 / 逐行表格）产生的每条广度记录必须进入
canonical-qa 增量索引才能被门户问答检索。索引写入是外部 HTTP 调用，
可能失败——因此不采用"导入时同步写索引"，而是落任务表由后台 worker
持久消费（四节要求：持久任务驱动、失败重启可重试、并发安全）。

- target_key 全局唯一：同一目标记录的重复入队只更新既有任务（op/payload
  覆盖 + 状态回 pending），最终态与最新一次操作一致，同记录不会重复召回；
- upsert/delete 在 canonical-qa 侧均为幂等操作，重复执行无副作用；
- worker 崩溃或重启后：processing 状态的任务由启动恢复逻辑重置回 pending。
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IndexTask(Base):
    __tablename__ = "breadth_index_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # "upsert" | "delete"
    op: Mapped[str] = mapped_column(String(16), nullable=False)
    # 目标文档 ID（= breadth_manual_records.id 的字符串形式），全局唯一
    target_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # 所属上传（如有）：用于聚合状态与重试；不设 FK——删除上传时任务须存活
    # 到索引删除真正完成（级联删除会吞掉待执行的 delete 任务）。
    upload_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # "pending" | "processing" | "done" | "failed"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 二.2 认领协议：rev=入队/覆盖自增修订号；claim_token=认领令牌；
    # lease_expires_at=租约到期（恢复只回收过期租约）。
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    not_before: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

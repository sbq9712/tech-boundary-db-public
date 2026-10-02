"""QA 增量索引重放状态（T3/G1，2026-10-02）。

canonical-qa 的增量索引损坏清空时会持久递增 reset epoch（数据卷内
reset-epoch.json）。api 侧 worker 每小时轮询 /api/health 的
incremental_reset_epoch：发现新 epoch 即把全部 status=done 且 op=upsert
的队列任务重置 pending（幂等重放——canonical (ksha,csha) 去重保证重复
写入安全；delete 不重放：墓碑独立持久不受清空影响）。

本表持久「已确认重放的 epoch」，api 重启后不会重复触发，也不会漏触发。
单行设计：id 恒为 1。
"""
from __future__ import annotations

import sqlalchemy
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QaReplayState(Base):
    __tablename__ = "qa_replay_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_confirmed_epoch: Mapped[int] = mapped_column(Integer, nullable=False,
                                                      default=0)
    updated_at: Mapped[object] = mapped_column(
        sqlalchemy.DateTime(timezone=True),
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(), nullable=False)

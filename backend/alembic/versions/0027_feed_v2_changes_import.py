"""feed-pkg/v2 增量导入 + 广度问答索引持久任务队列。

breadth_manual_records 新增：
- tag / topic / ai_picked：包内 AI 精选链路字段（tg/tp/aip），此前导入丢弃；
- source_version：feed 侧 per-key 单调版本（导入端据此"旧不覆新"）；
- stable_id / feed_key_digest：稳定 ID 与 feed 规范键摘要，
  UPDATE/DELETE 直接定位既有行；
- source_ref：逐行表格导入溯源（原文件/工作表/行号）。

breadth_index_tasks：持久索引任务队列（upsert/delete → canonical-qa），
失败可重试、重启可恢复；target_key 唯一保证同记录不重复召回。

breadth_import_sessions.details：v2 会话扩展计数
（added/updated/deleted/skipped_stale 等，旧计数列语义不变）。

uploaded_files.sync_breadth：行业追踪/ATSC 上传"同步上传到广度情报"选择
（默认否；选是后广度追踪可见且随资料生命周期一致）。

Revision ID: 0027_feed_v2_changes_import
Revises: 0026_github_incremental_import
Create Date: 2026-09-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_feed_v2_changes_import"
down_revision = "0026_github_incremental_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("breadth_manual_records", sa.Column("tag", sa.Text(), nullable=True))
    op.add_column("breadth_manual_records", sa.Column("topic", sa.Text(), nullable=True))
    op.add_column(
        "breadth_manual_records",
        sa.Column("ai_picked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "breadth_manual_records",
        sa.Column(
            "source_version", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "breadth_manual_records",
        sa.Column("stable_id", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_breadth_manual_records_stable_id",
        "breadth_manual_records", ["stable_id"],
    )
    op.add_column(
        "breadth_manual_records",
        sa.Column("feed_key_digest", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_breadth_manual_records_feed_key_digest",
        "breadth_manual_records", ["feed_key_digest"],
    )
    op.add_column(
        "breadth_manual_records",
        sa.Column("source_ref", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "breadth_manual_records",
        sa.Column("record_json", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "breadth_index_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("op", sa.String(length=16), nullable=False),
        sa.Column("target_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_breadth_index_tasks_status", "breadth_index_tasks", ["status"]
    )
    op.create_index(
        "ix_breadth_index_tasks_upload_id", "breadth_index_tasks", ["upload_id"]
    )

    op.add_column(
        "breadth_import_sessions",
        sa.Column("details", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "uploaded_files",
        sa.Column(
            "sync_breadth", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("uploaded_files", "sync_breadth")
    op.drop_column("breadth_import_sessions", "details")
    op.drop_index("ix_breadth_index_tasks_upload_id", table_name="breadth_index_tasks")
    op.drop_index("ix_breadth_index_tasks_status", table_name="breadth_index_tasks")
    op.drop_table("breadth_index_tasks")
    op.drop_column("breadth_manual_records", "record_json")
    op.drop_column("breadth_manual_records", "source_ref")
    op.drop_index(
        "ix_breadth_manual_records_feed_key_digest", table_name="breadth_manual_records"
    )
    op.drop_column("breadth_manual_records", "feed_key_digest")
    op.drop_index(
        "ix_breadth_manual_records_stable_id", table_name="breadth_manual_records"
    )
    op.drop_column("breadth_manual_records", "stable_id")
    op.drop_column("breadth_manual_records", "source_version")
    op.drop_column("breadth_manual_records", "ai_picked")
    op.drop_column("breadth_manual_records", "topic")
    op.drop_column("breadth_manual_records", "tag")

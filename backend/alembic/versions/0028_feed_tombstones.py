"""GitHub feed 删除墓碑（持久化删除版本，防陈旧包复活记录）。

breadth_feed_tombstones：应用 DELETE v 后按 feed 规范键摘要持久化
{deleted_version, deleted_content_hash}。更晚到达的乱序/补投递包重放
ADD/UPDATE v' <= v 时据此拒绝/判冲突；v' > v 视为合法重新上架并清除墓碑。
与删除行同一事务写入，崩溃不会出现「行已删、墓碑未记」的窗口。

Revision ID: 0028_feed_tombstones
Revises: 0027_feed_v2_changes_import
Create Date: 2026-09-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_feed_tombstones"
down_revision = "0027_feed_v2_changes_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "breadth_feed_tombstones",
        sa.Column("feed_key_digest", sa.String(length=32), primary_key=True),
        sa.Column("deleted_version", sa.Integer(), nullable=False),
        sa.Column("deleted_content_hash", sa.String(length=64), nullable=True),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("breadth_feed_tombstones")

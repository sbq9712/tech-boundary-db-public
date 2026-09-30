"""广度记录主导航可见开关（三.1）：breadth_manual_records.in_breadth_nav。

行业/ATSC 逐行导入默认不进主导航广度列表（行记录保留原栏目与门户检索）；
勾选「同步上传到广度情报」时为 True。既有行（含 GitHub 增量包导入记录）
保持 True——server_default 补齐存量，行为不变。

Revision ID: 0030_breadth_in_nav
Revises: 0029_index_task_claims
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0030_breadth_in_nav"
down_revision = "0029_index_task_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "breadth_manual_records",
        sa.Column("in_breadth_nav", sa.Boolean(), nullable=False,
                  server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("breadth_manual_records", "in_breadth_nav")

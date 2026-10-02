"""QA 增量索引重放状态表（T3/G1）：记录已确认的 canonical reset epoch。

Revision ID: 0032_qa_replay_state
Revises: 0031_feed_chain_state
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_qa_replay_state"
down_revision = "0031_feed_chain_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_replay_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_confirmed_epoch", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.execute("INSERT INTO qa_replay_state (id, last_confirmed_epoch) "
               "VALUES (1, 0) ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    op.drop_table("qa_replay_state")

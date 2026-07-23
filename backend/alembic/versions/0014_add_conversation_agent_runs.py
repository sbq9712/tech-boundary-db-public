"""add conversation agent run audit table

Revision ID: 0014_add_conversation_agent_runs
Revises: 0013_add_alert_created_at
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014_add_conv_agent_runs"
down_revision = "0013_add_alert_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.username", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("retrieval_summary", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conv_agent_runs_session_id", "conversation_agent_runs", ["session_id"])
    op.create_index("ix_conv_agent_runs_user_id", "conversation_agent_runs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_conv_agent_runs_user_id", "conversation_agent_runs")
    op.drop_index("ix_conv_agent_runs_session_id", "conversation_agent_runs")
    op.drop_table("conversation_agent_runs")

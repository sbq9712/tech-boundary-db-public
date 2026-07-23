"""persist retrieval summary on assistant messages

Revision ID: 0015_message_retrieval_summary
Revises: 0014_add_conv_agent_runs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015_message_retrieval_summary"
down_revision = "0014_add_conv_agent_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column(
            "retrieval_summary_json",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("conversation_messages", "retrieval_summary_json")

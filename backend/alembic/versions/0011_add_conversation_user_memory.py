"""add conversation and user_memory tables

Revision ID: 0011_add_conversation_user_memory
Revises: 0010_add_knowledge_artifacts
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_add_conv_user_memory"
down_revision = "0010_add_knowledge_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.username", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("topic_hint", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conv_sessions_user_id", "conversation_sessions", ["user_id"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("panel_recommendations_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conv_messages_session_id", "conversation_messages", ["session_id"])

    op.create_table(
        "user_research_profiles",
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.username", ondelete="CASCADE"), primary_key=True),
        sa.Column("preferred_domains", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("preferred_depth", sa.String(20), nullable=False, server_default="balanced"),
        sa.Column("language", sa.String(10), nullable=False, server_default="zh"),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "user_research_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.username", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(200), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.String(500), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_research_memory_user_id", "user_research_memory", ["user_id"])
    op.create_index("ix_user_research_memory_topic", "user_research_memory", ["topic"])


def downgrade() -> None:
    op.drop_index("ix_user_research_memory_topic", "user_research_memory")
    op.drop_index("ix_user_research_memory_user_id", "user_research_memory")
    op.drop_table("user_research_memory")
    op.drop_table("user_research_profiles")
    op.drop_index("ix_conv_messages_session_id", "conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conv_sessions_user_id", "conversation_sessions")
    op.drop_table("conversation_sessions")

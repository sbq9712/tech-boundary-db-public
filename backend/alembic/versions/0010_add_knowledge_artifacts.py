"""add knowledge_artifacts table

Revision ID: 0010_add_knowledge_artifacts
Revises: 0009_split_domains_tech_ind_nodes
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_add_knowledge_artifacts"
down_revision = "0009_split_tech_ind_nodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stable_id", sa.String(64), unique=True, nullable=True),
        sa.Column("artifact_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("vault_path", sa.Text(), nullable=True),
        sa.Column("absolute_path", sa.Text(), nullable=True),
        sa.Column("related_tech_node_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("related_ind_node_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("related_intelligence_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("related_observation_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("owner", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_knowledge_artifacts_stable_id", "knowledge_artifacts", ["stable_id"])
    op.create_index("ix_knowledge_artifacts_artifact_type", "knowledge_artifacts", ["artifact_type"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_artifacts_artifact_type", "knowledge_artifacts")
    op.drop_index("ix_knowledge_artifacts_stable_id", "knowledge_artifacts")
    op.drop_table("knowledge_artifacts")

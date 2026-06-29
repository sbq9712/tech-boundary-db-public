"""add parameter_observations table

Revision ID: 0008_add_parameter_observations
Revises: 0007_add_sources_evidence
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_add_parameter_observations"
down_revision = "0007_add_sources_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parameter_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stable_id", sa.String(64), unique=True, nullable=True),
        sa.Column("intelligence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("info_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("technology_node_id", sa.String(64), nullable=True),
        sa.Column("parameter_name", sa.String(200), nullable=False),
        sa.Column("parameter_type", sa.String(30), nullable=False, server_default="technical"),
        sa.Column("value_min", sa.Numeric(), nullable=True),
        sa.Column("value_max", sa.Numeric(), nullable=True),
        sa.Column("value_text", sa.String(500), nullable=True),
        sa.Column("unit", sa.String(100), nullable=True),
        sa.Column("condition_text", sa.Text(), nullable=True),
        sa.Column("scenario", sa.String(200), nullable=True),
        sa.Column("actor_or_company", sa.String(200), nullable=True),
        sa.Column("extraction_confidence", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("verification_status", sa.String(30), nullable=False, server_default="machine_extracted"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_param_obs_intelligence_id", "parameter_observations", ["intelligence_id"])
    op.create_index("ix_param_obs_source_id", "parameter_observations", ["source_id"])
    op.create_index("ix_param_obs_parameter_name", "parameter_observations", ["parameter_name"])
    op.create_index("ix_param_obs_tech_node_id", "parameter_observations", ["technology_node_id"])


def downgrade() -> None:
    op.drop_index("ix_param_obs_tech_node_id", "parameter_observations")
    op.drop_index("ix_param_obs_parameter_name", "parameter_observations")
    op.drop_index("ix_param_obs_source_id", "parameter_observations")
    op.drop_index("ix_param_obs_intelligence_id", "parameter_observations")
    op.drop_table("parameter_observations")

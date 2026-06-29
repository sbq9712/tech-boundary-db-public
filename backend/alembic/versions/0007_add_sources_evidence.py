"""add sources and evidence tables

Revision ID: 0007_add_sources_evidence
Revises: 0006_add_password_changed_at
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_add_sources_evidence"
down_revision = "0006_add_password_changed_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stable_id", sa.String(64), unique=True, nullable=True),
        sa.Column("external_ref", sa.String(128), unique=True, nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(1000), nullable=True),
        sa.Column("url_or_path", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by", sa.String(64), nullable=True),
        sa.Column("access_level", sa.String(20), nullable=False, server_default="public"),
        sa.Column("local_snapshot_path", sa.Text(), nullable=True),
        sa.Column("reliability_rating", sa.String(20), nullable=False, server_default="unrated"),
        sa.Column("domain", sa.String(100), nullable=True),
        sa.Column("subdomain", sa.String(100), nullable=True),
        sa.Column("needs_reclassification", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sources_stable_id", "sources", ["stable_id"])
    op.create_index("ix_sources_external_ref", "sources", ["external_ref"])
    op.create_index("ix_sources_source_type", "sources", ["source_type"])

    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stable_id", sa.String(64), unique=True, nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quote_or_excerpt", sa.Text(), nullable=True),
        sa.Column("page_or_location", sa.String(200), nullable=True),
        sa.Column("extracted_by", sa.String(64), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("local_asset_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_evidence_source_id", "evidence", ["source_id"])

    # Add primary_source_id FK to info_items (nullable, backfill not required)
    op.add_column("info_items", sa.Column("primary_source_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_info_items_primary_source", "info_items", "sources", ["primary_source_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_info_items_primary_source", "info_items", type_="foreignkey")
    op.drop_column("info_items", "primary_source_id")
    op.drop_index("ix_evidence_source_id", "evidence")
    op.drop_table("evidence")
    op.drop_index("ix_sources_source_type", "sources")
    op.drop_index("ix_sources_external_ref", "sources")
    op.drop_index("ix_sources_stable_id", "sources")
    op.drop_table("sources")

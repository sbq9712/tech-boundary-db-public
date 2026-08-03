"""add durable storage and taxonomy state to uploaded files

Revision ID: 0017_upload_ingestion_state
Revises: 0016_add_uploaded_files
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017_upload_ingestion_state"
down_revision = "0016_add_uploaded_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("uploaded_files", sa.Column("checksum_sha256", sa.String(length=64), nullable=True))
    op.add_column(
        "uploaded_files",
        sa.Column("storage_status", sa.String(length=20), nullable=False, server_default="stored"),
    )
    op.add_column("uploaded_files", sa.Column("taxonomy_version", sa.String(length=64), nullable=True))
    op.add_column("uploaded_files", sa.Column("primary_category", sa.Text(), nullable=True))
    op.add_column(
        "uploaded_files",
        sa.Column(
            "secondary_categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "uploaded_files",
        sa.Column(
            "classification_status",
            sa.String(length=30),
            nullable=False,
            server_default="legacy_unclassified",
        ),
    )
    op.add_column("uploaded_files", sa.Column("classification_confidence", sa.Float(), nullable=True))
    op.add_column("uploaded_files", sa.Column("classification_source", sa.String(length=20), nullable=True))
    op.add_column("uploaded_files", sa.Column("classification_reason", sa.Text(), nullable=True))
    op.add_column("uploaded_files", sa.Column("classification_error", sa.Text(), nullable=True))
    op.add_column(
        "uploaded_files",
        sa.Column("classification_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("uploaded_files", sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_uploaded_files_checksum_sha256", "uploaded_files", ["checksum_sha256"])
    op.create_index("ix_uploaded_files_taxonomy_version", "uploaded_files", ["taxonomy_version"])
    op.create_index("ix_uploaded_files_primary_category", "uploaded_files", ["primary_category"])
    op.create_index("ix_uploaded_files_classification_status", "uploaded_files", ["classification_status"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_classification_status", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_primary_category", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_taxonomy_version", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_checksum_sha256", table_name="uploaded_files")
    op.drop_column("uploaded_files", "classified_at")
    op.drop_column("uploaded_files", "classification_attempts")
    op.drop_column("uploaded_files", "classification_error")
    op.drop_column("uploaded_files", "classification_reason")
    op.drop_column("uploaded_files", "classification_source")
    op.drop_column("uploaded_files", "classification_confidence")
    op.drop_column("uploaded_files", "classification_status")
    op.drop_column("uploaded_files", "secondary_categories")
    op.drop_column("uploaded_files", "primary_category")
    op.drop_column("uploaded_files", "taxonomy_version")
    op.drop_column("uploaded_files", "storage_status")
    op.drop_column("uploaded_files", "checksum_sha256")

"""add uploaded_files table for the web upload feature

Revision ID: 0016_add_uploaded_files
Revises: 0015_message_retrieval_summary
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_add_uploaded_files"
down_revision = "0015_message_retrieval_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stored_filename", sa.String(length=128), nullable=False, unique=True),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("confidentiality", sa.String(length=20), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("domain_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("title_source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("submitted_by", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_uploaded_files_stored_filename", "uploaded_files", ["stored_filename"])
    op.create_index("ix_uploaded_files_submitted_by", "uploaded_files", ["submitted_by"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_submitted_by", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_stored_filename", table_name="uploaded_files")
    op.drop_table("uploaded_files")

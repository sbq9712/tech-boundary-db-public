"""add durable incremental embedding state to uploaded files

Revision ID: 0020_upload_embedding_state
Revises: 0019_clear_legacy_conversations
"""
from alembic import op
import sqlalchemy as sa


revision = "0020_upload_embedding_state"
down_revision = "0019_clear_legacy_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "uploaded_files",
        sa.Column(
            "embedding_status",
            sa.String(length=20),
            nullable=False,
            server_default="legacy_unindexed",
        ),
    )
    op.add_column("uploaded_files", sa.Column("embedding_model", sa.String(length=100), nullable=True))
    op.add_column("uploaded_files", sa.Column("embedding_dim", sa.Integer(), nullable=True))
    op.add_column("uploaded_files", sa.Column("embedding_error", sa.Text(), nullable=True))
    op.add_column(
        "uploaded_files",
        sa.Column("embedding_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("uploaded_files", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_uploaded_files_embedding_status", "uploaded_files", ["embedding_status"])
    op.alter_column("uploaded_files", "embedding_status", server_default=None)
    op.alter_column("uploaded_files", "embedding_attempts", server_default=None)
    op.alter_column("uploaded_files", "chunk_count", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_embedding_status", table_name="uploaded_files")
    op.drop_column("uploaded_files", "embedded_at")
    op.drop_column("uploaded_files", "chunk_count")
    op.drop_column("uploaded_files", "embedding_attempts")
    op.drop_column("uploaded_files", "embedding_error")
    op.drop_column("uploaded_files", "embedding_dim")
    op.drop_column("uploaded_files", "embedding_model")
    op.drop_column("uploaded_files", "embedding_status")

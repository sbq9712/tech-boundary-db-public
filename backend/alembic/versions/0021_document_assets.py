"""Docling asset manifest; no rewrite or deletion of existing upload/index data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_document_assets"
down_revision = "0020_upload_embedding_state"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "uploaded_files",
        sa.Column("document_assets", postgresql.JSONB(), nullable=True),
    )


def downgrade():
    op.drop_column("uploaded_files", "document_assets")

import sqlalchemy as sa
from alembic import op

revision = "0022_upload_document_date"
down_revision = "0021_document_assets"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "uploaded_files",
        sa.Column("document_date", sa.String(32), nullable=True),
    )


def downgrade():
    op.drop_column("uploaded_files", "document_date")

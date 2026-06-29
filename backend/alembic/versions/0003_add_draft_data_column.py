"""add draft_data column to info_items

Revision ID: 0003_add_draft_data_column
Revises: 0002_add_alert_columns
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0003_add_draft_data_column"
down_revision = "0002_add_alert_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "info_items",
        sa.Column(
            "draft_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("info_items", "draft_data")

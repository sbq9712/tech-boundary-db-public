"""add created_by column to info_items

Revision ID: 0005_add_created_by
Revises: 0004_add_users_last_modified_by
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_add_created_by"
down_revision = "0004_add_users_last_modified_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "info_items",
        sa.Column("created_by", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("info_items", "created_by")

"""add dedicated alert creation timestamp

Revision ID: 0013_add_alert_created_at
Revises: 0012_add_user_management
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_add_alert_created_at"
down_revision = "0012_add_user_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "info_items",
        sa.Column("alert_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE info_items "
        "SET alert_created_at = updated_at "
        "WHERE alert_status = 'active' AND alert_created_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("info_items", "alert_created_at")

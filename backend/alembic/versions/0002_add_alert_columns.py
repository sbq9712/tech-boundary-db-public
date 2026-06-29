"""add alert columns to info_items

Revision ID: 0002_add_alert_columns
Revises: 0001_init_tables
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_add_alert_columns"
down_revision = "0001_init_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("info_items", sa.Column("alert_status", sa.String(length=20), nullable=True))
    op.add_column("info_items", sa.Column("alert_source", sa.String(length=20), nullable=True))
    op.add_column(
        "info_items",
        sa.Column("alert_manual_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("info_items", sa.Column("alert_title", sa.String(length=500), nullable=True))
    op.add_column("info_items", sa.Column("alert_body", sa.Text(), nullable=True))
    op.add_column("info_items", sa.Column("alert_reviewer_comment", sa.Text(), nullable=True))
    op.add_column("info_items", sa.Column("alert_dismiss_reason", sa.Text(), nullable=True))
    op.add_column("info_items", sa.Column("alert_color", sa.String(length=20), nullable=True))
    op.add_column("info_items", sa.Column("alert_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("info_items", "alert_expires_at")
    op.drop_column("info_items", "alert_color")
    op.drop_column("info_items", "alert_dismiss_reason")
    op.drop_column("info_items", "alert_reviewer_comment")
    op.drop_column("info_items", "alert_body")
    op.drop_column("info_items", "alert_title")
    op.drop_column("info_items", "alert_manual_override")
    op.drop_column("info_items", "alert_source")
    op.drop_column("info_items", "alert_status")

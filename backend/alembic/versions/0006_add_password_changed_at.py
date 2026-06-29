"""add password_changed_at to users

Revision ID: 0006_add_password_changed_at
Revises: 0005_add_created_by
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_add_password_changed_at"
down_revision = "0005_add_created_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")

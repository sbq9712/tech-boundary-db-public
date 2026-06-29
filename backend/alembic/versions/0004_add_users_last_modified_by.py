"""add users table and last_modified_by column

Revision ID: 0004_add_users_last_modified_by
Revises: 0003_add_draft_data_column
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_users_last_modified_by"
down_revision = "0003_add_draft_data_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("username", sa.String(64), primary_key=True, nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.add_column(
        "info_items",
        sa.Column("last_modified_by", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("info_items", "last_modified_by")
    op.drop_table("users")

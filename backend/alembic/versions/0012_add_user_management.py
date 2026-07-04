"""add user management fields (display_name, role, is_active, last_login_at)

Revision ID: 0012_add_user_management
Revises: 0011_add_conv_user_memory
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_add_user_management"
down_revision = "0011_add_conv_user_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the four new columns. role and is_active need server defaults so the
    # NOT NULL constraint can be applied to an already-populated table.
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Set all pre-existing admin1-admin20 users to role='admin'.
    op.execute(
        "UPDATE users SET role = 'admin', is_active = true WHERE role = 'user'"
    )


def downgrade() -> None:
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "is_active")
    op.drop_column("users", "role")
    op.drop_column("users", "display_name")

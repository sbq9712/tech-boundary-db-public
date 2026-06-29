"""init tables

Revision ID: 0001_init_tables
Revises: 
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_init_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domains",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["domains.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "info_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("importance_score", sa.Integer(), nullable=False),
        sa.Column("is_new_tech", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("source_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("info_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("classification", sa.String(length=50), nullable=True),
    )

    op.create_table(
        "info_item_domains",
        sa.Column("info_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain_id", sa.String(length=64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["info_item_id"], ["info_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("info_item_id", "domain_id"),
    )

    op.create_index("ix_info_items_status", "info_items", ["status"])
    op.create_index("ix_info_items_published_at", "info_items", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_info_items_published_at", table_name="info_items")
    op.drop_index("ix_info_items_status", table_name="info_items")
    op.drop_table("info_item_domains")
    op.drop_table("info_items")
    op.drop_table("domains")

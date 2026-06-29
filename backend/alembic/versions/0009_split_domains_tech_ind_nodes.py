"""split domains into technology_nodes and industry_nodes

Revision ID: 0009_split_domains_tech_ind_nodes
Revises: 0008_add_parameter_observations
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_split_tech_ind_nodes"
down_revision = "0008_add_parameter_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "technology_nodes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.String(64), sa.ForeignKey("technology_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("node_type", sa.String(30), nullable=False, server_default="route"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "industry_nodes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.String(64), sa.ForeignKey("industry_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("node_type", sa.String(30), nullable=False, server_default="scenario"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "tech_industry_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_node_type", sa.String(10), nullable=False),
        sa.Column("from_node_id", sa.String(64), nullable=False),
        sa.Column("to_node_type", sa.String(10), nullable=False),
        sa.Column("to_node_id", sa.String(64), nullable=False),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tech_ind_rel_from", "tech_industry_relations", ["from_node_type", "from_node_id"])
    op.create_index("ix_tech_ind_rel_to", "tech_industry_relations", ["to_node_type", "to_node_id"])

    op.create_table(
        "info_item_tech_nodes",
        sa.Column("info_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("info_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tech_node_id", sa.String(64), sa.ForeignKey("technology_nodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_table(
        "info_item_ind_nodes",
        sa.Column("info_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("info_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ind_node_id", sa.String(64), sa.ForeignKey("industry_nodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Migrate existing domains → technology_nodes (all CCUS entries are tech classifications)
    op.execute("""
        INSERT INTO technology_nodes (id, name, parent_id, node_type, created_at, updated_at)
        SELECT id, name, parent_id, 'route', now(), now()
        FROM domains
    """)


def downgrade() -> None:
    op.drop_table("info_item_ind_nodes")
    op.drop_table("info_item_tech_nodes")
    op.drop_index("ix_tech_ind_rel_to", "tech_industry_relations")
    op.drop_index("ix_tech_ind_rel_from", "tech_industry_relations")
    op.drop_table("tech_industry_relations")
    op.drop_table("industry_nodes")
    op.drop_table("technology_nodes")

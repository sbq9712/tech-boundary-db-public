"""feed 发布序列链状态列（五.2）：breadth_import_sessions 链持久化。

接收端按 manifest(sequence/predecessor/manifest_digest/chain) 做
顺序/前驱/链完整性判定——每个已导入会话持久化其包序列与链头，
continuity 取 sequence 最大行：缺口（漏包）不阻塞数据应用
（per-key v 保护乱序/重放），后续包 predecessor 对齐即可继续推进。

Revision ID: 0031_feed_chain_state
Revises: 0030_breadth_in_nav
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_feed_chain_state"
down_revision = "0030_breadth_in_nav"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "breadth_import_sessions",
        sa.Column("package_sequence", sa.Integer(), nullable=True))
    op.add_column(
        "breadth_import_sessions",
        sa.Column("manifest_digest", sa.String(length=64), nullable=True))
    op.add_column(
        "breadth_import_sessions",
        sa.Column("chain_head", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_breadth_import_sessions_package_sequence",
        "breadth_import_sessions", ["package_sequence"])


def downgrade() -> None:
    op.drop_index(
        "ix_breadth_import_sessions_package_sequence",
        table_name="breadth_import_sessions")
    op.drop_column("breadth_import_sessions", "chain_head")
    op.drop_column("breadth_import_sessions", "manifest_digest")
    op.drop_column("breadth_import_sessions", "package_sequence")

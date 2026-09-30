"""索引任务认领协议（二.2）：修订号 + claim token + 租约。

breadth_index_tasks 增列：
- rev：每次入队/覆盖自增——worker 只能条件完成自己认领的任务版本；
- claim_token：认领时生成的随机令牌，完成/失败回写按令牌条件更新，
  执行期间被重新入队（rev 变化）后旧 worker 的完成写回被拒绝；
- lease_expires_at：认领租约到期时刻——恢复逻辑只回收过期租约，
  不重置其他活跃 worker 的任务。

Revision ID: 0029_index_task_claims
Revises: 0028_feed_tombstones
Create Date: 2026-09-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0029_index_task_claims"
down_revision = "0028_feed_tombstones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "breadth_index_tasks",
        sa.Column("rev", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "breadth_index_tasks",
        sa.Column("claim_token", sa.String(length=36), nullable=True))
    op.add_column(
        "breadth_index_tasks",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("breadth_index_tasks", "lease_expires_at")
    op.drop_column("breadth_index_tasks", "claim_token")
    op.drop_column("breadth_index_tasks", "rev")

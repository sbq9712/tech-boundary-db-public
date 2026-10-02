"""记录原始栏目归属（任务二 2.1）：breadth_manual_records.origin_section。

三逻辑源：breadth（GitHub 三源仓库情报 + 手工整理其他广度情报）、industry、atsc。
行业/ATSC 同步到广度只改展示入口（in_breadth_nav），检索归属原栏目——此前
记录行不携带栏目，问答检索/引用/图谱无法按源归属。

回填：upload_id → uploaded_files.primary_section（非空 FK，100% 可匹配——
Codex P2：upload 级联删除下不存在孤儿行，NULL 仅允许显式豁免清单，迁移内
校验）。回滚：drop_column（origin_section 可由 FK 重算，无数据损失）。

Revision ID: 0033_origin_section
Revises: 0032_qa_replay_state
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0033_origin_section"
down_revision = "0032_qa_replay_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "breadth_manual_records",
        sa.Column("origin_section", sa.String(length=20), nullable=True))
    op.create_index(
        "ix_breadth_manual_records_origin_section",
        "breadth_manual_records", ["origin_section"])
    # 回填：FK 可靠匹配（uploaded_files.primary_section 非空列）
    op.execute("""
        UPDATE breadth_manual_records r
        SET origin_section = CASE u.primary_section
                WHEN 'industry' THEN 'industry'
                WHEN 'atsc' THEN 'atsc'
                ELSE 'breadth' END
        FROM uploaded_files u
        WHERE r.upload_id = u.id AND r.origin_section IS NULL
    """)
    left = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM breadth_manual_records WHERE origin_section IS NULL"
    )).scalar()
    if left and int(left) > 0:
        # 不可追溯行存在（理论上 FK 全匹配不可能）：如实报错并放弃迁移，
        # 不允许静默猜测为 breadth（任务二 2.1：不猜测）
        raise RuntimeError(
            f"origin_section 回填后仍有 {left} 行无法归属（upload 匹配缺失），"
            f"拒绝默认猜测——请先修复孤儿引用再升级")


def downgrade() -> None:
    op.drop_index(
        "ix_breadth_manual_records_origin_section",
        table_name="breadth_manual_records")
    op.drop_column("breadth_manual_records", "origin_section")

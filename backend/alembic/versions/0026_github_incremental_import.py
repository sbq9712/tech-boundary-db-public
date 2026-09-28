"""GitHub 广度情报增量包导入：多记录入表 + 导入会话。

- breadth_manual_records.upload_id 放开唯一约束（1 个增量包 = N 条广度记录；
  原有 1 文件 1 记录语义由「其他广度情报」写入路径自行保证，读取层不变）。
- 新增 score / score_detail：增量包记录携带管线评分（sc / scd 五维），
  读取层按短键透出，广度页与上游记录同构展示。
- 新增 breadth_import_sessions：一包一会话，记录各类计数与幂等重放结果
  （docs/design/github-incremental-dedup.md 契约 §3/§4）。

Revision ID: 0026_github_incremental_import
Revises: 0025_breadth_manual_records
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0026_github_incremental_import"
down_revision = "0025_breadth_manual_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) upload_id 唯一约束放开（保留 ix_breadth_manual_records_upload_id 普通索引）
    op.drop_constraint(
        "breadth_manual_records_upload_id_key", "breadth_manual_records", type_="unique"
    )
    # 2) 管线评分字段（sc 字符串如 "7.8"；scd 五维 dict）
    op.add_column(
        "breadth_manual_records",
        sa.Column("score", sa.Text(), nullable=True),
    )
    op.add_column(
        "breadth_manual_records",
        sa.Column("score_detail", postgresql.JSONB(), nullable=True),
    )
    # 3) 导入会话表：一包一会话
    op.create_table(
        "breadth_import_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False, index=True),
        sa.Column("package_date", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("data_version", sa.String(length=64), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_upstream_conflict", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("package_deduplicated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("replayed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("failed_titles", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("breadth_import_sessions")
    op.drop_column("breadth_manual_records", "score_detail")
    op.drop_column("breadth_manual_records", "score")
    op.create_unique_constraint(
        "breadth_manual_records_upload_id_key", "breadth_manual_records", ["upload_id"]
    )

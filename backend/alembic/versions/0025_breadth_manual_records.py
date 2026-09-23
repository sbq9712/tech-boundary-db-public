"""其他广度情报真实入表：breadth_manual_records 持久层。

一个广度类上传文件对应一条广度总表记录（upload_id 唯一，级联删除），
读取层在只读上游分片之上合并本表。

Revision ID: 0025_breadth_manual_records
Revises: 0024_upload_primary_section
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025_breadth_manual_records"
down_revision = "0024_upload_primary_section"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "breadth_manual_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("user_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("document_date", sa.String(length=32), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("intelligence_type", sa.String(length=20), nullable=False, server_default="news"),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=True),
        sa.Column("key_parameters", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_breadth_manual_records_upload_id", "breadth_manual_records", ["upload_id"])


def downgrade() -> None:
    op.drop_index("ix_breadth_manual_records_upload_id", table_name="breadth_manual_records")
    op.drop_table("breadth_manual_records")

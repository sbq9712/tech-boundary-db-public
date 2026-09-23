"""移除 uploaded_files 的三个废弃业务字段：size_bytes / confidentiality / source_type。

- size_bytes：不再作为业务字段持久化；下载响应的 Content-Length 改由实际文件计算。
- confidentiality / source_type：密级与来源类型从资料库中彻底移除（UI、API、AI 填充同步取消）。
- 仅新增迁移，不改写任何历史迁移；已有库按链升级，新库全链直建。
- 保留 checksum_sha256、mime_type、original_filename、stored_filename 等存储事实字段。

Revision ID: 0023_drop_upload_legacy_fields
Revises: 0022_upload_document_date
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_drop_upload_legacy_fields"
down_revision = "0022_upload_document_date"
branch_labels = None
depends_on = None

TABLE = "uploaded_files"
COLUMNS = ("size_bytes", "confidentiality", "source_type")


def upgrade() -> None:
    for column in COLUMNS:
        op.drop_column(TABLE, column)


def downgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("source_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column("confidentiality", sa.String(length=20), nullable=True),
    )
    op.add_column(
        TABLE,
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column(TABLE, "size_bytes", server_default=None)

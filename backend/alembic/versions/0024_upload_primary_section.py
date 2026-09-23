"""资料库三分区：uploaded_files 增加 primary_section / breadth_source。

- primary_section: breadth(广度追踪) | industry(行业追踪) | atsc(ATSC内部报告)
- breadth_source:  仅 primary_section=breadth 时有效: github(GitHub广度情报) | other(其他广度情报)
- 后端校验组合合法性；存量行默认 industry（当前库中资料已清空，仅为升级链兜底）。

Revision ID: 0024_upload_primary_section
Revises: 0023_drop_upload_legacy_fields
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0024_upload_primary_section"
down_revision = "0023_drop_upload_legacy_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "uploaded_files",
        sa.Column("primary_section", sa.String(length=20), nullable=False, server_default="industry"),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("breadth_source", sa.String(length=20), nullable=True),
    )
    op.create_index("ix_uploaded_files_primary_section", "uploaded_files", ["primary_section"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_primary_section", table_name="uploaded_files")
    op.drop_column("uploaded_files", "breadth_source")
    op.drop_column("uploaded_files", "primary_section")

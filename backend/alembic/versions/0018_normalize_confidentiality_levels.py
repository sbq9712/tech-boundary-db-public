"""normalize confidentiality labels to the current three-level taxonomy

Revision ID: 0018_confidentiality_levels
Revises: 0017_upload_ingestion_state
"""

from alembic import op


revision = "0018_confidentiality_levels"
down_revision = "0017_upload_ingestion_state"
branch_labels = None
depends_on = None


def _normalize(table: str, column: str) -> None:
    op.execute(
        f"""
        UPDATE {table}
        SET {column} = NULL
        WHERE {column} IS NOT NULL AND btrim({column}) = ''
        """
    )
    op.execute(
        f"""
        UPDATE {table}
        SET {column} = CASE lower(btrim({column}))
            WHEN '公开' THEN '公开'
            WHEN 'public' THEN '公开'
            WHEN '内部' THEN '内部'
            WHEN 'internal' THEN '内部'
            WHEN '管理员' THEN '管理员'
            WHEN 'admin' THEN '管理员'
            ELSE '内部'
        END
        WHERE {column} IS NOT NULL
        """
    )


def upgrade() -> None:
    _normalize("uploaded_files", "confidentiality")
    _normalize("info_items", "classification")

    op.create_check_constraint(
        "ck_uploaded_files_confidentiality_level",
        "uploaded_files",
        "confidentiality IS NULL OR confidentiality IN ('公开', '内部', '管理员')",
    )
    op.create_check_constraint(
        "ck_info_items_classification_level",
        "info_items",
        "classification IS NULL OR classification IN ('公开', '内部', '管理员')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_info_items_classification_level", "info_items", type_="check")
    op.drop_constraint("ck_uploaded_files_confidentiality_level", "uploaded_files", type_="check")

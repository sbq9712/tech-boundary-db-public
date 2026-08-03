"""clear legacy user conversation history before canonical QA rollout

Revision ID: 0019_clear_legacy_conversations
Revises: 0018_confidentiality_levels
"""

from alembic import op


revision = "0019_clear_legacy_conversations"
down_revision = "0018_confidentiality_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Foreign keys use ON DELETE CASCADE, so messages and agent runs are removed
    # while users, research memory, uploads and all other domain data are kept.
    op.execute("DELETE FROM conversation_sessions")


def downgrade() -> None:
    # Conversation content cannot be reconstructed after the explicit rollout cleanup.
    pass

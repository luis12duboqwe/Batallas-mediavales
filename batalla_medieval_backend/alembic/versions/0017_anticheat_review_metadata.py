"""Add BM-0074 anti-cheat human review metadata.

Revision ID: 0017_anticheat_review_metadata
Revises: 0016_admin_support_moderation
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_anticheat_review_metadata"
down_revision = "0016_admin_support_moderation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("anti_cheat_flags") as batch_op:
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("resolution_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("anti_cheat_flags") as batch_op:
        batch_op.drop_column("resolution_reason")
        batch_op.drop_column("reviewed_at")

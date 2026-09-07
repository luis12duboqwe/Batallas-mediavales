"""Add BM-0074 anti-cheat review metadata and persistent rate buckets.

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

    op.create_table(
        "anti_cheat_rate_buckets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action_key", sa.String(length=96), nullable=False),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "action_key",
            name="uq_anticheat_rate_bucket_user_action",
        ),
    )
    op.create_index(
        "ix_anticheat_rate_buckets_user_id",
        "anti_cheat_rate_buckets",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_anticheat_rate_buckets_user_id",
        table_name="anti_cheat_rate_buckets",
    )
    op.drop_table("anti_cheat_rate_buckets")

    with op.batch_alter_table("anti_cheat_flags") as batch_op:
        batch_op.drop_column("resolution_reason")
        batch_op.drop_column("reviewed_at")

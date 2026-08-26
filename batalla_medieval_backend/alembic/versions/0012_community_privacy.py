"""Add world-scoped social blocking.

Revision ID: 0012_community_privacy
Revises: 0011_movement_hero_assignment
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_community_privacy"
down_revision = "0011_movement_hero_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("blocker_id", sa.Integer(), nullable=False),
        sa.Column("blocked_id", sa.Integer(), nullable=False),
        sa.Column("world_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "blocker_id",
            "blocked_id",
            "world_id",
            name="uq_user_block_pair_world",
        ),
    )
    op.create_index("ix_user_blocks_id", "user_blocks", ["id"], unique=False)
    op.create_index(
        "ix_user_blocks_blocker_world",
        "user_blocks",
        ["blocker_id", "world_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_blocks_blocked_world",
        "user_blocks",
        ["blocked_id", "world_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_blocks_blocked_world", table_name="user_blocks")
    op.drop_index("ix_user_blocks_blocker_world", table_name="user_blocks")
    op.drop_index("ix_user_blocks_id", table_name="user_blocks")
    op.drop_table("user_blocks")

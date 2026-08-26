"""Scope persistent player messages to a game world.

Revision ID: 0013_message_world_scope
Revises: 0012_community_privacy
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_message_world_scope"
down_revision = "0012_community_privacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing messages cannot be backfilled safely when two players share more
    # than one world, so legacy rows remain nullable. All BM-0070 writes require
    # a concrete world_id and all player-facing lists are world-scoped.
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("world_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_messages_world_id_worlds",
            "worlds",
            ["world_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_messages_world_id", ["world_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_index("ix_messages_world_id")
        batch_op.drop_constraint("fk_messages_world_id_worlds", type_="foreignkey")
        batch_op.drop_column("world_id")

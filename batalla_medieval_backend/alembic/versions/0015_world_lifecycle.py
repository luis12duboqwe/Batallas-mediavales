"""Add explicit world lifecycle state.

Revision ID: 0015_world_lifecycle
Revises: 0014_achievement_progress_world_scope
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_world_lifecycle"
down_revision = "0014_achievement_progress_world_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("worlds") as batch_op:
        batch_op.add_column(sa.Column("lifecycle_status", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("lifecycle_changed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("pause_started_at", sa.DateTime(), nullable=True))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE worlds
            SET lifecycle_status = CASE
                WHEN is_active THEN 'open'
                WHEN ended_at IS NOT NULL THEN 'closed'
                ELSE 'paused'
            END,
            lifecycle_changed_at = COALESCE(ended_at, created_at, CURRENT_TIMESTAMP),
            pause_started_at = NULL
            """
        )
    )

    with op.batch_alter_table("worlds") as batch_op:
        batch_op.alter_column("lifecycle_status", existing_type=sa.String(length=16), nullable=False)
        batch_op.alter_column("lifecycle_changed_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.create_index("ix_worlds_lifecycle_status", ["lifecycle_status"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE worlds
            SET is_active = CASE WHEN lifecycle_status = 'open' THEN TRUE ELSE FALSE END
            """
        )
    )
    with op.batch_alter_table("worlds") as batch_op:
        batch_op.drop_index("ix_worlds_lifecycle_status")
        batch_op.drop_column("pause_started_at")
        batch_op.drop_column("lifecycle_changed_at")
        batch_op.drop_column("lifecycle_status")

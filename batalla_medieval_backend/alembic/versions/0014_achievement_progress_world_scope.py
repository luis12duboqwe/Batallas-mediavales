"""Scope achievement progress to one world.

Revision ID: 0014_achievement_progress_world_scope
Revises: 0013_message_world_scope
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_achievement_progress_world_scope"
down_revision = "0013_message_world_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("achievement_progress") as batch_op:
        batch_op.add_column(sa.Column("world_id", sa.Integer(), nullable=True))

    # Preserve legacy progress only when the user's world can be resolved
    # unambiguously. Ambiguous multi-world rows are intentionally not copied
    # into every world because that would leak progress across servers.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT ap.id, ap.user_id
            FROM achievement_progress ap
            WHERE ap.world_id IS NULL
            """
        )
    ).fetchall()
    for row in rows:
        world_ids = [
            int(value[0])
            for value in bind.execute(
                sa.text(
                    """
                    SELECT DISTINCT world_id
                    FROM player_worlds
                    WHERE user_id = :user_id
                    ORDER BY world_id
                    """
                ),
                {"user_id": row.user_id},
            ).fetchall()
        ]
        if len(world_ids) == 1:
            bind.execute(
                sa.text(
                    "UPDATE achievement_progress SET world_id = :world_id WHERE id = :id"
                ),
                {"world_id": world_ids[0], "id": row.id},
            )
        else:
            bind.execute(
                sa.text("DELETE FROM achievement_progress WHERE id = :id"),
                {"id": row.id},
            )

    with op.batch_alter_table("achievement_progress") as batch_op:
        batch_op.drop_constraint("uq_user_achievement", type_="unique")
        batch_op.alter_column("world_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_achievement_progress_world_id_worlds",
            "worlds",
            ["world_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_user_achievement_world",
            ["user_id", "achievement_id", "world_id"],
        )
        batch_op.create_index("ix_achievement_progress_world_id", ["world_id"], unique=False)


def downgrade() -> None:
    # A user can have the same medal in multiple worlds. Downgrade keeps one
    # deterministic row per (user, achievement) before restoring the legacy key.
    bind = op.get_bind()
    duplicate_ids = bind.execute(
        sa.text(
            """
            SELECT id
            FROM achievement_progress ap
            WHERE EXISTS (
                SELECT 1
                FROM achievement_progress earlier
                WHERE earlier.user_id = ap.user_id
                  AND earlier.achievement_id = ap.achievement_id
                  AND earlier.id < ap.id
            )
            """
        )
    ).fetchall()
    for row in duplicate_ids:
        bind.execute(
            sa.text("DELETE FROM achievement_progress WHERE id = :id"),
            {"id": row.id},
        )

    with op.batch_alter_table("achievement_progress") as batch_op:
        batch_op.drop_index("ix_achievement_progress_world_id")
        batch_op.drop_constraint("uq_user_achievement_world", type_="unique")
        batch_op.drop_constraint(
            "fk_achievement_progress_world_id_worlds",
            type_="foreignkey",
        )
        batch_op.drop_column("world_id")
        batch_op.create_unique_constraint(
            "uq_user_achievement",
            ["user_id", "achievement_id"],
        )

"""Persist optional hero assignment on military movements.

Revision ID: 0011_movement_hero_assignment
Revises: 0010
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_movement_hero_assignment"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite cannot ALTER constraints in place. Validation intentionally runs
    # the full migration chain on SQLite, so keep the column, FK and index in
    # one batch copy-and-move operation. PostgreSQL uses the same migration
    # contract without requiring a dialect-specific branch.
    with op.batch_alter_table("movements") as batch_op:
        batch_op.add_column(sa.Column("hero_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_movements_hero_id_heroes",
            "heroes",
            ["hero_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_movements_hero_id", ["hero_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("movements") as batch_op:
        batch_op.drop_index("ix_movements_hero_id")
        batch_op.drop_constraint("fk_movements_hero_id_heroes", type_="foreignkey")
        batch_op.drop_column("hero_id")

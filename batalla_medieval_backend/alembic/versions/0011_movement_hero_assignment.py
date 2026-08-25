"""Persist optional hero assignment on military movements.

Revision ID: 0011_movement_hero_assignment
Revises: 0010_hero_world_adventure_outcome
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_movement_hero_assignment"
down_revision = "0010_hero_world_adventure_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("movements", sa.Column("hero_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_movements_hero_id_heroes",
        "movements",
        "heroes",
        ["hero_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_movements_hero_id", "movements", ["hero_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_movements_hero_id", table_name="movements")
    op.drop_constraint("fk_movements_hero_id_heroes", "movements", type_="foreignkey")
    op.drop_column("movements", "hero_id")

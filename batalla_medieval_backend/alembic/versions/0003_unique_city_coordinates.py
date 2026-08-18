"""enforce unique city coordinates per world

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_NAME = "ux_cities_world_xy"


def upgrade() -> None:
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(
            """
            SELECT world_id, x, y, COUNT(*) AS duplicate_count
            FROM cities
            GROUP BY world_id, x, y
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).mappings().first()
    if duplicate:
        raise RuntimeError(
            "Cannot enforce unique city coordinates: duplicate city tile "
            f"world={duplicate['world_id']} x={duplicate['x']} y={duplicate['y']} "
            f"count={duplicate['duplicate_count']}"
        )

    op.create_index(
        _INDEX_NAME,
        "cities",
        ["world_id", "x", "y"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="cities")

"""add settlement types and expansion points

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-23

BM-0061 introduces player expansion through cities and camps. Existing cities
remain full cities. Expansion points belong to a player's membership in one
world, preventing points earned in one world from being spent in another.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cities",
        sa.Column(
            "settlement_type",
            sa.String(length=16),
            nullable=False,
            server_default="city",
        ),
    )
    op.add_column(
        "player_world",
        sa.Column(
            "expansion_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("player_world", "expansion_points")
    op.drop_column("cities", "settlement_type")

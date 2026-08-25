"""persist versioned world PvE tick state

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-25

BM-0067 pins the barbarian/oasis ruleset per world and records the last
successfully committed PvE tick. This lets the dedicated worker retry a failed
tick without rerolling or applying regeneration twice after restart.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PVE_RULES_VERSION = "2026.08.25-bm0067-v1"


def upgrade() -> None:
    op.add_column(
        "worlds",
        sa.Column(
            "pve_rules_version",
            sa.String(),
            nullable=False,
            server_default=PVE_RULES_VERSION,
        ),
    )
    op.add_column(
        "worlds",
        sa.Column("pve_last_tick_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("worlds", "pve_last_tick_at")
    op.drop_column("worlds", "pve_rules_version")

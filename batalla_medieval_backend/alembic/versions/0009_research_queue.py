"""add timed research queue

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-23

BM-0062 replaces instant unit research with a durable server-authoritative
queue. One city may research one technology at a time; the exact paid cost is
stored so cancellation can refund the recorded payment rather than recomputing
against a later balance version.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_queue",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("tech_name", sa.String(), nullable=False),
        sa.Column("finish_time", sa.DateTime(), nullable=False),
        sa.Column("paid_cost", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_queue_id", "research_queue", ["id"], unique=False)
    op.create_index("ix_research_queue_city_id", "research_queue", ["city_id"], unique=False)
    op.create_index("ux_research_queue_city", "research_queue", ["city_id"], unique=True)
    op.create_index(
        "ux_research_queue_city_tech",
        "research_queue",
        ["city_id", "tech_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_research_queue_city_tech", table_name="research_queue")
    op.drop_index("ux_research_queue_city", table_name="research_queue")
    op.drop_index("ix_research_queue_city_id", table_name="research_queue")
    op.drop_index("ix_research_queue_id", table_name="research_queue")
    op.drop_table("research_queue")

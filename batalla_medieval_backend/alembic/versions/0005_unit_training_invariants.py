"""unit research and training invariants

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_no_duplicates(connection, table: str, columns: tuple[str, ...], label: str) -> None:
    group_by = ", ".join(columns)
    duplicate = connection.execute(
        sa.text(
            f"""
            SELECT {group_by}, COUNT(*) AS duplicate_count
            FROM {table}
            GROUP BY {group_by}
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).mappings().first()
    if duplicate:
        details = ", ".join(f"{column}={duplicate[column]}" for column in columns)
        raise RuntimeError(
            f"Cannot enforce {label} uniqueness: duplicate {details} "
            f"count={duplicate['duplicate_count']}"
        )


def upgrade() -> None:
    connection = op.get_bind()
    _assert_no_duplicates(
        connection,
        "research",
        ("city_id", "tech_name"),
        "research per city/unit",
    )
    _assert_no_duplicates(
        connection,
        "troops",
        ("city_id", "unit_type"),
        "troop balance per city/unit",
    )

    op.add_column(
        "troop_queue",
        sa.Column("paid_cost", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ux_research_city_tech",
        "research",
        ["city_id", "tech_name"],
        unique=True,
    )
    op.create_index(
        "ux_troops_city_unit",
        "troops",
        ["city_id", "unit_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_troops_city_unit", table_name="troops")
    op.drop_index("ux_research_city_tech", table_name="research")
    op.drop_column("troop_queue", "paid_cost")

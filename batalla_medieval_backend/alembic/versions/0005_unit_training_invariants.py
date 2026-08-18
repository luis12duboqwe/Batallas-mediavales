"""unit research and training invariants

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-18
"""

from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RESEARCHABLE_UNITS = {
    "heavy_infantry",
    "archer",
    "fast_cavalry",
    "heavy_cavalry",
    "spy",
    "ram",
    "catapult",
    "noble",
}


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


def _backfill_research_state(connection) -> None:
    """Promote legacy JSON progress into Research rows, then sync the mirror."""

    city_table = sa.table(
        "cities",
        sa.column("id", sa.Integer()),
        sa.column("researched_units", sa.JSON()),
    )
    research_table = sa.table(
        "research",
        sa.column("city_id", sa.Integer()),
        sa.column("tech_name", sa.String()),
        sa.column("level", sa.Integer()),
    )

    existing_pairs = {
        (int(row.city_id), str(row.tech_name))
        for row in connection.execute(
            sa.select(research_table.c.city_id, research_table.c.tech_name)
        )
    }

    city_rows = list(
        connection.execute(
            sa.select(city_table.c.id, city_table.c.researched_units)
        ).mappings()
    )
    for row in city_rows:
        city_id = int(row["id"])
        for unit in list(row["researched_units"] or []):
            unit_name = str(unit)
            pair = (city_id, unit_name)
            if unit_name not in RESEARCHABLE_UNITS or pair in existing_pairs:
                continue
            connection.execute(
                research_table.insert().values(
                    city_id=city_id,
                    tech_name=unit_name,
                    level=1,
                )
            )
            existing_pairs.add(pair)

    researched_by_city: dict[int, list[str]] = defaultdict(list)
    for row in connection.execute(
        sa.select(research_table.c.city_id, research_table.c.tech_name)
        .order_by(research_table.c.city_id, research_table.c.tech_name)
    ):
        if row.tech_name != "basic_infantry":
            researched_by_city[int(row.city_id)].append(str(row.tech_name))

    for row in city_rows:
        current = list(row["researched_units"] or [])
        merged = ["basic_infantry"]
        merged.extend(unit for unit in current if unit != "basic_infantry")
        merged.extend(researched_by_city.get(int(row["id"]), []))
        merged = list(dict.fromkeys(merged))
        connection.execute(
            city_table.update()
            .where(city_table.c.id == row["id"])
            .values(researched_units=merged)
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
    _backfill_research_state(connection)
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

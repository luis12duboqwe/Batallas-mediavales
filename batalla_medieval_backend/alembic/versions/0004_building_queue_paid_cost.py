"""persist building queue paid cost and uniqueness invariants

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
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
        "buildings",
        ("city_id", "name"),
        "building per city/type",
    )
    _assert_no_duplicates(
        connection,
        "building_queue",
        ("city_id", "building_type"),
        "building queue per city/type",
    )

    op.add_column(
        "building_queue",
        sa.Column("paid_cost", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ux_buildings_city_name",
        "buildings",
        ["city_id", "name"],
        unique=True,
    )
    op.create_index(
        "ux_building_queue_city_type",
        "building_queue",
        ["city_id", "building_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_building_queue_city_type", table_name="building_queue")
    op.drop_index("ux_buildings_city_name", table_name="buildings")
    op.drop_column("building_queue", "paid_cost")

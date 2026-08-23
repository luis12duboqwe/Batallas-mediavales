"""migrate canonical economy to wood, stone, iron and gold

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-23

The migration preserves clay balances 1:1 as stone and rewrites persisted
resource identifiers/JSON payloads. Gold starts at zero for every existing
city so the migration never creates an economic windfall. A live downgrade is
refused once any gold has been accrued or assigned; production rollback must
then restore the pre-migration database snapshot rather than discard value.
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_JSON_RESOURCE_COLUMNS = (
    ("movements", "resources"),
    ("building_queue", "paid_cost"),
    ("troop_queue", "paid_cost"),
)


def _rewrite_resource_payload(value: Any, old: str, new: str) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, dict):
        return {
            (new if key == old else key): _rewrite_resource_payload(item, old, new)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_resource_payload(item, old, new) for item in value]
    return value


def _rewrite_json_column(table_name: str, column_name: str, old: str, new: str) -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    table = sa.Table(
        table_name,
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(column_name, sa.JSON()),
    )
    rows = bind.execute(sa.select(table.c.id, table.c[column_name])).mappings().all()
    for row in rows:
        original = row[column_name]
        rewritten = _rewrite_resource_payload(original, old, new)
        if rewritten != original:
            bind.execute(
                table.update().where(table.c.id == row["id"]).values({column_name: rewritten})
            )


def _rewrite_persisted_identifiers(old: str, new: str) -> None:
    op.execute(
        sa.text(
            "UPDATE market_offers SET offer_type = :new WHERE offer_type = :old"
        ).bindparams(old=old, new=new)
    )
    op.execute(
        sa.text(
            "UPDATE market_offers SET request_type = :new WHERE request_type = :old"
        ).bindparams(old=old, new=new)
    )
    op.execute(
        sa.text(
            "UPDATE oases SET resource_type = :new WHERE resource_type = :old"
        ).bindparams(old=old, new=new)
    )
    for table_name, column_name in _JSON_RESOURCE_COLUMNS:
        _rewrite_json_column(table_name, column_name, old, new)


def upgrade() -> None:
    # Rename rather than copy so every existing clay balance becomes the exact
    # stone balance with no rounding or conversion loss.
    with op.batch_alter_table("cities") as batch_op:
        batch_op.alter_column(
            "clay",
            new_column_name="stone",
            existing_type=sa.Float(),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column(
                "gold",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )

    _rewrite_persisted_identifiers("clay", "stone")


def downgrade() -> None:
    bind = op.get_bind()
    gold_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM cities WHERE ABS(gold) > 0.000000001")
    ).scalar_one()
    if gold_count:
        raise RuntimeError(
            "BM-0060 downgrade would discard non-zero gold. Restore the "
            "pre-migration database backup instead."
        )

    _rewrite_persisted_identifiers("stone", "clay")

    with op.batch_alter_table("cities") as batch_op:
        batch_op.drop_column("gold")
        batch_op.alter_column(
            "stone",
            new_column_name="clay",
            existing_type=sa.Float(),
            existing_nullable=False,
        )

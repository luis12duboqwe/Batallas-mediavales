"""migrate live economy to wood, stone, iron and gold

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-23

The legacy ``clay`` balance is preserved 1:1 as ``stone``. Existing cities
receive the same starter gold granted to newly created cities. Persisted
resource identifiers and JSON payloads are rewritten so in-flight movements,
queued refunds and historical reports keep their meaning after the rename.

Downgrade is intended for the pre-traffic rollback path used by deployment:
``stone`` is copied back to ``clay`` and JSON/string identifiers are restored.
Gold has no representation before 0007, so a rollback after players have
started earning/spending gold must restore the pre-migration database snapshot
instead of relying on schema downgrade alone.
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

STARTER_GOLD = 500.0


def _rewrite_resource(value: Any, source: str, target: str) -> Any:
    if isinstance(value, dict):
        rewritten: dict[Any, Any] = {}
        for key, item in value.items():
            new_key = target if key == source else key
            rewritten[new_key] = _rewrite_resource(item, source, target)
        return rewritten
    if isinstance(value, list):
        return [_rewrite_resource(item, source, target) for item in value]
    if value == source:
        return target
    return value


def _rewrite_json_column(table_name: str, column_name: str, source: str, target: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name not in columns:
        return

    table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
    rows = bind.execute(sa.select(table.c.id, table.c[column_name])).all()
    for row_id, raw_value in rows:
        if raw_value is None:
            continue
        value = raw_value
        if isinstance(raw_value, str):
            try:
                value = json.loads(raw_value)
            except (TypeError, ValueError):
                continue
        rewritten = _rewrite_resource(value, source, target)
        if rewritten != value:
            bind.execute(
                table.update().where(table.c.id == row_id).values({column_name: rewritten})
            )


def _rewrite_report_content(source: str, target: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "reports" not in inspector.get_table_names():
        return
    reports = sa.Table("reports", sa.MetaData(), autoload_with=bind)
    rows = bind.execute(sa.select(reports.c.id, reports.c.content)).all()
    for report_id, content in rows:
        if not content:
            continue
        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            continue
        rewritten = _rewrite_resource(parsed, source, target)
        if rewritten != parsed:
            bind.execute(
                reports.update()
                .where(reports.c.id == report_id)
                .values(content=json.dumps(rewritten, ensure_ascii=False))
            )


def _rewrite_string_column(table_name: str, column_name: str, source: str, target: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name not in columns:
        return
    table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
    bind.execute(
        table.update()
        .where(table.c[column_name] == source)
        .values({column_name: target})
    )


def _rewrite_payloads(source: str, target: str) -> None:
    for table_name, column_name in (
        ("movements", "resources"),
        ("building_queue", "paid_cost"),
        ("troop_queue", "paid_cost"),
        ("quests", "reward"),
        ("quests", "requirements"),
        ("quest_progress", "progress"),
    ):
        _rewrite_json_column(table_name, column_name, source, target)

    _rewrite_string_column("market_offers", "offer_type", source, target)
    _rewrite_string_column("market_offers", "request_type", source, target)
    _rewrite_string_column("oases", "resource_type", source, target)
    _rewrite_report_content(source, target)


def upgrade() -> None:
    # SQLite requires batch mode for a portable column rename while PostgreSQL
    # emits a normal ALTER TABLE RENAME COLUMN.
    with op.batch_alter_table("cities") as batch_op:
        batch_op.alter_column(
            "clay",
            new_column_name="stone",
            existing_type=sa.Float(),
            existing_nullable=True,
        )
        batch_op.add_column(
            sa.Column(
                "gold",
                sa.Float(),
                nullable=False,
                server_default=sa.text(str(STARTER_GOLD)),
            )
        )

    _rewrite_payloads("clay", "stone")


def downgrade() -> None:
    _rewrite_payloads("stone", "clay")

    with op.batch_alter_table("cities") as batch_op:
        batch_op.drop_column("gold")
        batch_op.alter_column(
            "stone",
            new_column_name="clay",
            existing_type=sa.Float(),
            existing_nullable=True,
        )

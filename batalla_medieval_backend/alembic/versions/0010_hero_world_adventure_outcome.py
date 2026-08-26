"""world-scope heroes and persist auditable adventure outcomes

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-25

BM-0068 makes hero progression world-isolated and makes adventure claims
retry-safe. Existing heroes inherit their world from their current city (or the
user's active/membership world as fallback). Adventure outcome, seed and rules
version are stored so a committed claim can be replayed without rerolling or
paying twice.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQLITE_NAMING = {
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _single_user_unique_name(bind) -> str:
    if bind.dialect.name == "sqlite":
        # 0001 created this constraint unnamed. Batch mode can address it after
        # reflecting with a naming convention.
        return "uq_heroes_user_id"
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("heroes"):
        if constraint.get("column_names") == ["user_id"] and constraint.get("name"):
            return str(constraint["name"])
    raise RuntimeError("Could not locate legacy heroes(user_id) unique constraint")


def upgrade() -> None:
    bind = op.get_bind()
    naming = _SQLITE_NAMING if bind.dialect.name == "sqlite" else None
    legacy_unique = _single_user_unique_name(bind)

    with op.batch_alter_table("heroes", naming_convention=naming) as batch:
        batch.add_column(sa.Column("world_id", sa.Integer(), nullable=True))
        batch.drop_constraint(legacy_unique, type_="unique")

    heroes = sa.Table("heroes", sa.MetaData(), autoload_with=bind)
    cities = sa.Table("cities", sa.MetaData(), autoload_with=bind)
    users = sa.Table("users", sa.MetaData(), autoload_with=bind)
    memberships = sa.Table("player_world", sa.MetaData(), autoload_with=bind)

    # Prefer the hero's current city because it is the gameplay state the legacy
    # hero already belonged to. The two fallbacks only handle older/orphan rows.
    bind.execute(
        heroes.update()
        .where(heroes.c.world_id.is_(None))
        .values(
            world_id=sa.select(cities.c.world_id)
            .where(cities.c.id == heroes.c.city_id)
            .scalar_subquery()
        )
    )
    bind.execute(
        heroes.update()
        .where(heroes.c.world_id.is_(None))
        .values(
            world_id=sa.select(users.c.world_id)
            .where(users.c.id == heroes.c.user_id)
            .scalar_subquery()
        )
    )
    bind.execute(
        heroes.update()
        .where(heroes.c.world_id.is_(None))
        .values(
            world_id=sa.select(sa.func.min(memberships.c.world_id))
            .where(memberships.c.user_id == heroes.c.user_id)
            .scalar_subquery()
        )
    )

    missing = bind.execute(
        sa.select(sa.func.count()).select_from(heroes).where(heroes.c.world_id.is_(None))
    ).scalar_one()
    if missing:
        raise RuntimeError(f"Cannot world-scope {missing} legacy hero row(s)")

    with op.batch_alter_table("heroes", naming_convention=naming) as batch:
        batch.alter_column("world_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_heroes_world_id_worlds", "worlds", ["world_id"], ["id"])
        batch.create_unique_constraint("uq_heroes_user_world", ["user_id", "world_id"])
        batch.create_index("ix_heroes_world_id", ["world_id"], unique=False)

    with op.batch_alter_table("adventures") as batch:
        batch.add_column(sa.Column("rules_version", sa.String(), nullable=True))
        batch.add_column(sa.Column("outcome_seed", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("result", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    naming = _SQLITE_NAMING if bind.dialect.name == "sqlite" else None

    # A downgrade can only restore the old one-hero-per-account model when no
    # user has heroes in multiple worlds. Operational rollback must restore a DB
    # snapshot instead if BM-0068 has already created such state.
    heroes = sa.Table("heroes", sa.MetaData(), autoload_with=bind)
    duplicates = bind.execute(
        sa.select(heroes.c.user_id)
        .group_by(heroes.c.user_id)
        .having(sa.func.count(heroes.c.id) > 1)
    ).first()
    if duplicates:
        raise RuntimeError(
            "Cannot downgrade BM-0068 after a user has heroes in multiple worlds; restore the pre-migration snapshot"
        )

    with op.batch_alter_table("adventures") as batch:
        batch.drop_column("result")
        batch.drop_column("outcome_seed")
        batch.drop_column("rules_version")

    with op.batch_alter_table("heroes", naming_convention=naming) as batch:
        batch.drop_index("ix_heroes_world_id")
        batch.drop_constraint("uq_heroes_user_world", type_="unique")
        batch.drop_constraint("fk_heroes_world_id_worlds", type_="foreignkey")
        batch.drop_column("world_id")
        batch.create_unique_constraint("uq_heroes_user_id", ["user_id"])

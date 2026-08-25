"""world-scope heroes and persist deterministic adventure outcomes

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-25

BM-0068 turns the legacy global hero/adventure prototype into durable,
world-scoped game state. Heroes become unique per player/world and adventures
persist the rules identity, audit seed and claimed result so retries cannot mint
rewards twice.
"""

from __future__ import annotations

import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HERO_RULES_VERSION = "2026.08.25-bm0068-v1"
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _legacy_user_unique_name(bind) -> str:
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("heroes"):
        if list(constraint.get("column_names") or []) == ["user_id"]:
            return constraint.get("name") or "uq_heroes_user_id"
    return "uq_heroes_user_id"


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("heroes", sa.Column("world_id", sa.Integer(), nullable=True))

    # Prefer the hero's current city, then the user's selected world, then an
    # actual membership. The final fallback only keeps an orphaned prototype
    # row migratable; normal API access still requires world membership.
    bind.execute(sa.text(
        """
        UPDATE heroes
        SET world_id = (SELECT cities.world_id FROM cities WHERE cities.id = heroes.city_id)
        WHERE world_id IS NULL AND city_id IS NOT NULL
        """
    ))
    bind.execute(sa.text(
        """
        UPDATE heroes
        SET world_id = (SELECT users.world_id FROM users WHERE users.id = heroes.user_id)
        WHERE world_id IS NULL
          AND (SELECT users.world_id FROM users WHERE users.id = heroes.user_id) IS NOT NULL
        """
    ))
    bind.execute(sa.text(
        """
        UPDATE heroes
        SET world_id = (
            SELECT MIN(player_world.world_id)
            FROM player_world
            WHERE player_world.user_id = heroes.user_id
        )
        WHERE world_id IS NULL
        """
    ))
    fallback_world = bind.execute(sa.text("SELECT MIN(id) FROM worlds")).scalar()
    if fallback_world is not None:
        bind.execute(
            sa.text("UPDATE heroes SET world_id = :world_id WHERE world_id IS NULL"),
            {"world_id": int(fallback_world)},
        )
    missing = bind.execute(sa.text("SELECT COUNT(*) FROM heroes WHERE world_id IS NULL")).scalar()
    if int(missing or 0):
        raise RuntimeError("Cannot world-scope legacy heroes because no world exists")

    old_unique = _legacy_user_unique_name(bind)
    with op.batch_alter_table(
        "heroes",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(old_unique, type_="unique")
        batch_op.alter_column("world_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_heroes_world_id_worlds", "worlds", ["world_id"], ["id"]
        )
        batch_op.create_unique_constraint(
            "uq_heroes_user_world", ["user_id", "world_id"]
        )
        batch_op.create_index("ix_heroes_world_id", ["world_id"], unique=False)

    op.add_column(
        "adventures",
        sa.Column("rules_version", sa.String(), nullable=True),
    )
    op.add_column("adventures", sa.Column("seed", sa.String(length=64), nullable=True))
    op.add_column("adventures", sa.Column("result_json", sa.JSON(), nullable=True))

    adventure_rows = bind.execute(sa.text("SELECT id FROM adventures ORDER BY id")).all()
    for (adventure_id,) in adventure_rows:
        seed = hashlib.sha256(
            f"{HERO_RULES_VERSION}:legacy-adventure:{int(adventure_id)}".encode("utf-8")
        ).hexdigest()
        bind.execute(
            sa.text(
                "UPDATE adventures SET rules_version = :version, seed = :seed WHERE id = :id"
            ),
            {
                "version": HERO_RULES_VERSION,
                "seed": seed,
                "id": int(adventure_id),
            },
        )

    with op.batch_alter_table("adventures", recreate="always") as batch_op:
        batch_op.alter_column(
            "rules_version", existing_type=sa.String(), nullable=False
        )
        batch_op.alter_column(
            "seed", existing_type=sa.String(length=64), nullable=False
        )
        batch_op.create_index("ix_adventures_hero_id", ["hero_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    # A pre-BM-0068 schema can only represent one hero per user. Keep the
    # lowest-id hero deterministically and remove dependent package rows for
    # additional worlds before restoring the legacy uniqueness constraint.
    duplicate_ids = [
        int(row[0])
        for row in bind.execute(sa.text(
            """
            SELECT h.id
            FROM heroes h
            WHERE EXISTS (
                SELECT 1 FROM heroes earlier
                WHERE earlier.user_id = h.user_id AND earlier.id < h.id
            )
            """
        )).all()
    ]
    if duplicate_ids:
        ids = ",".join(str(value) for value in duplicate_ids)
        bind.execute(sa.text(f"DELETE FROM hero_items WHERE hero_id IN ({ids})"))
        bind.execute(sa.text(f"DELETE FROM adventures WHERE hero_id IN ({ids})"))
        bind.execute(sa.text(f"DELETE FROM heroes WHERE id IN ({ids})"))

    with op.batch_alter_table("adventures", recreate="always") as batch_op:
        batch_op.drop_index("ix_adventures_hero_id")
        batch_op.drop_column("result_json")
        batch_op.drop_column("seed")
        batch_op.drop_column("rules_version")

    with op.batch_alter_table(
        "heroes",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_index("ix_heroes_world_id")
        batch_op.drop_constraint("uq_heroes_user_world", type_="unique")
        batch_op.drop_constraint("fk_heroes_world_id_worlds", type_="foreignkey")
        batch_op.drop_column("world_id")
        batch_op.create_unique_constraint("uq_heroes_user_id", ["user_id"])

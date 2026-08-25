"""Idempotent bootstrap data for a fresh Batallas Medievales database."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal
from .services import balance, hero as hero_service, pve

logger = logging.getLogger(__name__)

DEFAULT_WORLD_NAME = "Mundo 1"
DEFAULT_WORLD_MAP_SIZE = 100

# Fixed, valid map coordinates. They deliberately avoid water tiles and are
# stable across runs so a restored/new database gets the same initial world.
CANONICAL_BARBARIANS = (
    (20, 15),
    (30, 25),
    (40, 35),
    (50, 45),
    (60, 55),
    (70, 65),
    (80, 75),
    (15, 80),
)

# Compatibility aliases kept for callers that still import the historical
# alpha baseline. BM-0067 fresh worlds use the tier profiles in ``services.pve``.
BARBARIAN_BUILDINGS = balance.BARBARIAN_STARTING_BUILDINGS
BARBARIAN_TROOPS = balance.BARBARIAN_STARTING_TROOPS


@dataclass(frozen=True)
class SeedResult:
    world_id: int
    world_created: bool
    barbarians_created: int


def _get_or_create_world(db: Session) -> tuple[models.World, bool]:
    world = (
        db.query(models.World)
        .filter(models.World.name == DEFAULT_WORLD_NAME)
        .one_or_none()
    )
    if world:
        # Never rewrite rules of a world that may already contain player
        # progress. PvE reconciliation reads/preserves its pinned manifest.
        return world, False

    world = models.World(
        name=DEFAULT_WORLD_NAME,
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=DEFAULT_WORLD_MAP_SIZE,
        special_rules="",
        is_active=True,
    )
    db.add(world)
    db.flush()
    return world, True


def _validate_canonical_coordinates(db: Session, world: models.World) -> None:
    """Refuse to reinterpret a real player settlement as canonical PvE state.

    A player-owned city whose name still starts with ``Aldea Bárbara`` is a
    legitimately conquered canonical village and must be preserved. Any other
    player city on a reserved coordinate indicates incompatible/corrupt seed
    state and remains a hard failure, matching the pre-BM-0067 contract.
    """

    for x, y in CANONICAL_BARBARIANS:
        existing = (
            db.query(models.City)
            .filter(
                models.City.world_id == world.id,
                models.City.x == x,
                models.City.y == y,
            )
            .one_or_none()
        )
        if (
            existing is not None
            and existing.owner_id is not None
            and not str(existing.name or "").startswith("Aldea Bárbara")
        ):
            raise RuntimeError(
                "Canonical seed coordinate is occupied by a player city: "
                f"world={world.id} x={x} y={y}"
            )


def seed_game(db: Session) -> SeedResult:
    """Create/reconcile the canonical initial world without resetting progress."""

    world, world_created = _get_or_create_world(db)

    try:
        _validate_canonical_coordinates(db, world)
        created = pve.ensure_world_pve(
            db,
            world,
            canonical_barbarian_coords=CANONICAL_BARBARIANS,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Hero/items are outside the MVP cut, but keeping the existing item catalog
    # in this single bootstrap process avoids a regression while removing the
    # old per-API-startup seed side effect.
    hero_service.seed_items(db)

    return SeedResult(
        world_id=world.id,
        world_created=world_created,
        barbarians_created=int(created["barbarians_created"]),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        result = seed_game(db)
        logger.info(
            "Canonical seed complete: world_id=%s world_created=%s barbarians_created=%s",
            result.world_id,
            result.world_created,
            result.barbarians_created,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

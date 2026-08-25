"""Idempotent bootstrap data for a fresh Batallas Medievales database."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal
from .services import hero as hero_service, pve_rules, world_gen

logger = logging.getLogger(__name__)

DEFAULT_WORLD_NAME = "Mundo 1"
DEFAULT_WORLD_MAP_SIZE = 100


@dataclass(frozen=True)
class SeedResult:
    world_id: int
    world_created: bool
    barbarians_created: int
    oases_created: int = 0


def _get_or_create_world(db: Session) -> tuple[models.World, bool]:
    world = (
        db.query(models.World)
        .filter(models.World.name == DEFAULT_WORLD_NAME)
        .one_or_none()
    )
    if world:
        # Never rewrite rules/content of a world that may already contain
        # player progress. BM-0067 pins PvE identity on world creation.
        return world, False

    world = models.World(
        name=DEFAULT_WORLD_NAME,
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=DEFAULT_WORLD_MAP_SIZE,
        special_rules="",
        is_active=True,
        pve_rules_version=pve_rules.PVE_RULES_VERSION,
    )
    db.add(world)
    db.flush()
    return world, True


def seed_game(db: Session) -> SeedResult:
    """Create the canonical initial world without resetting existing progress."""

    world, world_created = _get_or_create_world(db)
    barbarians_created = 0
    oases_created = 0

    try:
        if world_created:
            barbarians_created, oases_created = world_gen.populate_world_pve(db, world)
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
        barbarians_created=barbarians_created,
        oases_created=oases_created,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        result = seed_game(db)
        logger.info(
            "Canonical seed complete: world_id=%s world_created=%s "
            "barbarians_created=%s oases_created=%s pve_rules=%s",
            result.world_id,
            result.world_created,
            result.barbarians_created,
            result.oases_created,
            pve_rules.PVE_RULES_VERSION,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

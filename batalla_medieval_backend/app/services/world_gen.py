import random

from sqlalchemy.orm import Session

from .. import models


def create_world(db: Session, name: str, speed: float = 1.0) -> models.World:
    """Create or reconcile one deterministic PvE world for tools/tests.

    BM-0067 owns barbarian and oasis generation in ``services.pve``. Keeping
    this helper as a thin entrypoint prevents tests/admin tooling from creating
    a second, incompatible PvE catalog (the legacy implementation generated 50
    bare barbarian cities plus zero-defense ``rat``/``spider`` oases).
    """

    from . import pve

    world = db.query(models.World).filter(models.World.name == name).one_or_none()
    if world is None:
        world = models.World(
            name=name,
            speed_modifier=speed,
            resource_modifier=1.0,
            map_size=100,
            is_active=True,
        )
        db.add(world)
        db.flush()

    pve.ensure_world_pve(db, world)
    db.commit()
    db.refresh(world)
    return world


def get_tile_type(x: int, y: int) -> str:
    """Return a deterministic tile type without mutating global RNG state."""

    rng = random.Random(f"{x},{y}")
    value = rng.random()
    if value < 0.1:
        return "water"
    if value < 0.3:
        return "mountain"
    if value < 0.5:
        return "forest"
    return "grass"


def _coordinate_is_free(db: Session, world_id: int, x: int, y: int) -> bool:
    city_exists = (
        db.query(models.City.id)
        .filter(
            models.City.world_id == world_id,
            models.City.x == x,
            models.City.y == y,
        )
        .first()
        is not None
    )
    if city_exists:
        return False

    oasis_exists = (
        db.query(models.Oasis.id)
        .filter(
            models.Oasis.world_id == world_id,
            models.Oasis.x == x,
            models.Oasis.y == y,
        )
        .first()
        is not None
    )
    return not oasis_exists


def find_spawn_location(db: Session, world_id: int, map_size: int) -> tuple[int, int]:
    """Find a valid, unoccupied spawn location for a new city."""

    if map_size <= 0:
        raise ValueError("World map size must be positive")

    rng = random.SystemRandom()

    # Try random locations first for performance.
    for _ in range(50):
        x = rng.randrange(map_size)
        y = rng.randrange(map_size)

        if _coordinate_is_free(db, world_id, x, y) and get_tile_type(x, y) != "water":
            return x, y

    # Fall back to a deterministic expanding search around the map center.
    center_x, center_y = map_size // 2, map_size // 2
    for radius in range(0, map_size):
        for offset_x in range(-radius, radius + 1):
            for offset_y in range(-radius, radius + 1):
                if radius and abs(offset_x) != radius and abs(offset_y) != radius:
                    continue

                x, y = center_x + offset_x, center_y + offset_y
                if not (0 <= x < map_size and 0 <= y < map_size):
                    continue

                if _coordinate_is_free(db, world_id, x, y) and get_tile_type(x, y) != "water":
                    return x, y

    raise ValueError("No valid spawn location found")
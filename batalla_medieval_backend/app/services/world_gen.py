import random

from sqlalchemy.orm import Session

from .. import models


def create_world(db: Session, name: str, speed: float = 1.0) -> models.World:
    """Create a deterministic generated world once for tools/tests.

    Production bootstrap uses ``app.seed``. This helper remains available for
    tests and admin tooling, but repeated calls with the same world name are
    idempotent and all generated coordinates respect ``map_size``.
    """

    existing = db.query(models.World).filter(models.World.name == name).one_or_none()
    if existing:
        return existing

    world = models.World(
        name=name,
        speed_modifier=speed,
        resource_modifier=1.0,
        map_size=100,
        is_active=True,
    )
    db.add(world)
    db.flush()

    rng = random.Random(f"batallas-medievales:{name}:{speed}")
    occupied: set[tuple[int, int]] = set()

    # Generate deterministic barbarian villages on valid, non-water tiles.
    attempts = 0
    while len(occupied) < 50 and attempts < 2000:
        attempts += 1
        x = rng.randrange(world.map_size)
        y = rng.randrange(world.map_size)
        coord = (x, y)
        if coord in occupied or get_tile_type(x, y) == "water":
            continue

        occupied.add(coord)
        db.add(
            models.City(
                name="Aldea Bárbara",
                world_id=world.id,
                x=x,
                y=y,
                owner_id=None,
                wood=1000,
                clay=1000,
                iron=1000,
                tile_type=get_tile_type(x, y),
            )
        )

    oasis_count = 0
    attempts = 0
    oasis_coords: set[tuple[int, int]] = set()
    while oasis_count < 20 and attempts < 2000:
        attempts += 1
        x = rng.randrange(world.map_size)
        y = rng.randrange(world.map_size)
        coord = (x, y)
        if coord in occupied or coord in oasis_coords:
            continue

        oasis_coords.add(coord)
        oasis_count += 1
        db.add(
            models.Oasis(
                world_id=world.id,
                x=x,
                y=y,
                resource_type=rng.choice(["wood", "clay", "iron", "crop"]),
                bonus_percent=25 if rng.random() > 0.2 else 50,
                troops={
                    "rat": rng.randint(5, 15),
                    "spider": rng.randint(3, 8),
                },
            )
        )

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


def find_spawn_location(db: Session, world_id: int, map_size: int) -> tuple[int, int]:
    """Find a valid spawn location for a new city."""

    rng = random.SystemRandom()

    # Try random locations first for performance.
    for _ in range(50):
        x = rng.randrange(map_size)
        y = rng.randrange(map_size)

        if not db.query(models.City).filter(
            models.City.world_id == world_id,
            models.City.x == x,
            models.City.y == y,
        ).first():
            if get_tile_type(x, y) != "water":
                return x, y

    # Fall back to a deterministic expanding search around the map center.
    center_x, center_y = map_size // 2, map_size // 2
    for radius in range(1, map_size):
        for offset_x in range(-radius, radius + 1):
            for offset_y in range(-radius, radius + 1):
                if abs(offset_x) != radius and abs(offset_y) != radius:
                    continue

                x, y = center_x + offset_x, center_y + offset_y
                if not (0 <= x < map_size and 0 <= y < map_size):
                    continue

                occupied = db.query(models.City).filter(
                    models.City.world_id == world_id,
                    models.City.x == x,
                    models.City.y == y,
                ).first()
                if not occupied and get_tile_type(x, y) != "water":
                    return x, y

    raise ValueError("No valid spawn location found")

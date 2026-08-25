from __future__ import annotations

import random
from typing import Iterable

from sqlalchemy.orm import Session

from .. import models
from . import balance, pve_rules


def create_world(db: Session, name: str, speed: float = 1.0) -> models.World:
    """Create one deterministic generated world with final BM-0067 PvE content.

    Repeated calls with the same world name remain idempotent. A newly created
    world is populated exactly once; running this helper later never replenishes
    conquered/damaged neutral content.
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
        pve_rules_version=pve_rules.PVE_RULES_VERSION,
    )
    db.add(world)
    db.flush()

    populate_world_pve(db, world)
    db.commit()
    db.refresh(world)
    return world


def _create_barbarian(
    db: Session,
    world: models.World,
    *,
    index: int,
    x: int,
    y: int,
) -> models.City:
    difficulty, profile = pve_rules.barbarian_profile(
        world_id=world.id,
        x=x,
        y=y,
        rules_version=world.pve_rules_version,
    )
    resources = profile["starting_resources"]
    city = models.City(
        name=f"Aldea Bárbara {index:02d} · {difficulty}",
        world_id=world.id,
        x=x,
        y=y,
        owner_id=None,
        wood=resources["wood"],
        stone=resources["stone"],
        iron=resources["iron"],
        gold=resources["gold"],
        population_max=int(profile["population_max"]),
        loyalty=balance.LOYALTY_MAX,
        tile_type=get_tile_type(x, y),
    )
    db.add(city)
    db.flush()

    for building_name, level in profile["buildings"]:
        db.add(
            models.Building(
                city_id=city.id,
                name=building_name,
                level=int(level),
            )
        )
    for unit_type, quantity in profile["starting_troops"]:
        if unit_type not in balance.UNIT_COMBAT_STATS:
            raise RuntimeError(f"PvE generator contains unknown combat unit: {unit_type}")
        db.add(
            models.Troop(
                city_id=city.id,
                unit_type=unit_type,
                quantity=int(quantity),
            )
        )
    return city


def _create_oasis(
    db: Session,
    world: models.World,
    *,
    x: int,
    y: int,
    rng: random.Random,
) -> models.Oasis:
    _, profile = pve_rules.oasis_profile(
        world_id=world.id,
        x=x,
        y=y,
        rules_version=world.pve_rules_version,
    )
    guards = {
        unit: int(quantity)
        for unit, quantity in profile["guard_target"].items()
    }
    unknown = set(guards) - set(balance.UNIT_COMBAT_STATS)
    if unknown:
        raise RuntimeError(f"PvE oasis contains unknown combat units: {sorted(unknown)}")

    oasis = models.Oasis(
        world_id=world.id,
        x=x,
        y=y,
        resource_type=rng.choice(list(balance.RESOURCE_FIELDS)),
        bonus_percent=int(profile["bonus_percent"]),
        troops=guards,
    )
    db.add(oasis)
    return oasis


def _next_free_land_coordinate(
    *,
    rng: random.Random,
    map_size: int,
    occupied: set[tuple[int, int]],
    max_attempts: int,
) -> tuple[int, int]:
    for _ in range(max_attempts):
        x = rng.randrange(map_size)
        y = rng.randrange(map_size)
        coordinate = (x, y)
        if coordinate in occupied or get_tile_type(x, y) == "water":
            continue
        occupied.add(coordinate)
        return coordinate
    raise RuntimeError("Could not allocate deterministic PvE coordinate")


def populate_world_pve(
    db: Session,
    world: models.World,
    *,
    reserved_coordinates: Iterable[tuple[int, int]] = (),
) -> tuple[int, int]:
    """Populate a fresh world with deterministic, versioned neutral content."""

    if world.id is None:
        db.flush()
    if str(world.pve_rules_version or "") != pve_rules.PVE_RULES_VERSION:
        raise ValueError(
            f"Unsupported PvE rules version: {world.pve_rules_version!r}"
        )

    existing_city_count = (
        db.query(models.City.id)
        .filter(models.City.world_id == world.id)
        .count()
    )
    existing_oasis_count = (
        db.query(models.Oasis.id)
        .filter(models.Oasis.world_id == world.id)
        .count()
    )
    if existing_city_count or existing_oasis_count:
        raise ValueError("PvE population is only valid for an empty world")

    barbarian_count, oasis_count = pve_rules.world_content_counts(world.map_size)
    rng = random.Random(
        f"batallas-medievales:pve:{world.name}:{world.map_size}:"
        f"{world.speed_modifier}:{world.pve_rules_version}"
    )
    occupied = {tuple(map(int, coordinate)) for coordinate in reserved_coordinates}
    attempts = max(int(world.map_size) ** 2 * 4, 2_000)

    for index in range(1, barbarian_count + 1):
        x, y = _next_free_land_coordinate(
            rng=rng,
            map_size=int(world.map_size),
            occupied=occupied,
            max_attempts=attempts,
        )
        _create_barbarian(db, world, index=index, x=x, y=y)

    for _ in range(oasis_count):
        x, y = _next_free_land_coordinate(
            rng=rng,
            map_size=int(world.map_size),
            occupied=occupied,
            max_attempts=attempts,
        )
        _create_oasis(db, world, x=x, y=y, rng=rng)

    db.flush()
    return barbarian_count, oasis_count


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

    # Try random locations first for performance. Player spawn randomness does
    # not affect authoritative combat/PvE simulation outcomes.
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

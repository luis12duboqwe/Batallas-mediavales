from typing import Dict, Tuple

from sqlalchemy.orm import Session

from .. import models
from . import combat, production, world_gen

FOUNDING_COST = {"wood": 800.0, "clay": 800.0, "iron": 800.0}
STARTER_BUILDINGS = [
    {"name": "town_hall", "level": 1},
    {"name": "barracks", "level": 1},
]


def _validate_troops_available(city: models.City, troops_sent: Dict[str, int]):
    for unit, amount in troops_sent.items():
        if amount <= 0:
            raise ValueError("Conquest troop amounts must be positive")
        troop = next((t for t in city.troops if t.unit_type == unit), None)
        if not troop or troop.quantity < amount:
            raise ValueError(f"Not enough {unit} in the city")


def _validate_conquest_target(
    attacker_city: models.City,
    target_city: models.City,
) -> None:
    """Enforce the canonical v1 rule: only neutral/barbarian cities are conquerable."""

    if attacker_city.owner_id is None:
        raise ValueError("Attacker city must belong to a player")
    if attacker_city.id == target_city.id:
        raise ValueError("A city cannot conquer itself")
    if attacker_city.world_id != target_city.world_id:
        raise ValueError("Cross-world conquest is not allowed")
    if target_city.owner_id is not None:
        raise ValueError("Player cities cannot be conquered")


def _lock_conquest_cities(
    db: Session,
    attacker_city_id: int,
    target_city_id: int,
) -> tuple[models.City, models.City]:
    """Lock both city rows in deterministic id order to serialize conquest races."""

    rows = (
        db.query(models.City)
        .filter(models.City.id.in_([attacker_city_id, target_city_id]))
        .order_by(models.City.id.asc())
        .with_for_update()
        .populate_existing()
        .all()
    )
    by_id = {city.id: city for city in rows}
    attacker = by_id.get(attacker_city_id)
    target = by_id.get(target_city_id)
    if attacker is None:
        raise ValueError("Attacker city not found")
    if target is None:
        raise ValueError("Target city not found")
    return attacker, target


def _apply_losses(city: models.City, losses: Dict[str, int]):
    for unit, loss in losses.items():
        troop = next((t for t in city.troops if t.unit_type == unit), None)
        if troop:
            troop.quantity = max(0, troop.quantity - int(loss))
            if troop.quantity < 0:
                raise ValueError("Troop quantity cannot become negative")


def resolve_conquest(
    db: Session,
    attacker_city: models.City,
    target_city: models.City,
    troops_sent: Dict[str, int],
) -> Tuple[bool, bool]:
    """Resolve an instant conquest attempt against a barbarian city only.

    The target city row is locked before the ownership rule is checked again, so
    two concurrent players cannot both conquer the same neutral city. Combat is
    delegated to the canonical battle engine instead of maintaining a second
    combat implementation.
    """

    try:
        attacker_city, target_city = _lock_conquest_cities(
            db,
            attacker_city.id,
            target_city.id,
        )
        _validate_conquest_target(attacker_city, target_city)
        _validate_troops_available(attacker_city, troops_sent)

        production.recalculate_resources(db, attacker_city, commit=False)
        production.recalculate_resources(db, target_city, commit=False)

        battle_result = combat.resolve_battle(
            attacker_city,
            target_city,
            troops_sent,
        )
        _apply_losses(attacker_city, battle_result.get("attacker_losses", {}))
        _apply_losses(target_city, battle_result.get("defender_losses", {}))

        attacker_survivors = battle_result.get("attacker_survivors", {})
        defender_survivors = battle_result.get("defender_survivors", {})
        victory = (
            sum(int(amount) for amount in attacker_survivors.values()) > 0
            and sum(int(amount) for amount in defender_survivors.values()) == 0
        )
        conquered = bool(battle_result.get("conquest", False))

        db.add(attacker_city)
        db.add(target_city)
        db.commit()
        db.refresh(attacker_city)
        db.refresh(target_city)
        return victory, conquered
    except Exception:
        db.rollback()
        raise


def found_city(
    db: Session,
    owner: models.User,
    origin_city: models.City,
    name: str,
    x: int,
    y: int,
) -> models.City:
    """Found a city without allowing concurrent requests to double-spend."""

    origin_city, production_gains = production.lock_and_recalculate_resources(
        db, origin_city
    )

    existing_city = (
        db.query(models.City)
        .filter(
            models.City.world_id == origin_city.world_id,
            models.City.x == x,
            models.City.y == y,
        )
        .first()
    )
    if existing_city:
        db.rollback()
        raise ValueError("Another city already exists at those coordinates")

    if not production.check_cost(origin_city, FOUNDING_COST):
        db.rollback()
        raise ValueError("Not enough resources to found a new city")
    production.pay_cost(origin_city, FOUNDING_COST)

    tile_type = world_gen.get_tile_type(x, y)
    new_city = models.City(
        name=name,
        x=x,
        y=y,
        owner_id=owner.id,
        world_id=origin_city.world_id,
        loyalty=100.0,
        tile_type=tile_type,
    )
    db.add(new_city)
    db.flush()

    for building in STARTER_BUILDINGS:
        starter = models.Building(
            city_id=new_city.id,
            name=building["name"],
            level=building["level"],
        )
        db.add(starter)

    db.commit()
    db.refresh(new_city)
    production.record_resource_gains(db, origin_city, production_gains)
    return new_city

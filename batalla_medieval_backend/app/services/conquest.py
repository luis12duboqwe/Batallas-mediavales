from typing import Dict, Tuple

from sqlalchemy.orm import Session

from .. import models
from . import combat, production, world_gen

LOYALTY_DROP_PER_SUCCESS = 25.0
FOUNDING_COST = {"wood": 800.0, "clay": 800.0, "iron": 800.0}
STARTER_BUILDINGS = [
    {"name": "town_hall", "level": 1},
    {"name": "barracks", "level": 1},
]


def _validate_troops_available(city: models.City, troops_sent: Dict[str, int]):
    for unit, amount in troops_sent.items():
        troop = next((t for t in city.troops if t.unit_type == unit), None)
        if not troop or troop.quantity < amount:
            raise ValueError(f"Not enough {unit} in the city")


def _apply_losses(city: models.City, losses: Dict[str, int]):
    for unit, loss in losses.items():
        troop = next((t for t in city.troops if t.unit_type == unit), None)
        if troop:
            troop.quantity = max(0, troop.quantity - loss)


def _calculate_strength(troops_sent: Dict[str, int]) -> int:
    return sum(troops_sent.values())


def resolve_conquest(
    db: Session, attacker_city: models.City, target_city: models.City, troops_sent: Dict[str, int]
) -> Tuple[bool, bool]:
    production.recalculate_resources(db, attacker_city)
    production.recalculate_resources(db, target_city)
    _validate_troops_available(attacker_city, troops_sent)

    defender_troops = {troop.unit_type: troop.quantity for troop in target_city.troops}

    battle_result = combat.simulate_round(troops_sent, defender_troops)
    attacker_losses = battle_result["attacker_losses"]
    defender_losses = battle_result["defender_losses"]

    _apply_losses(attacker_city, attacker_losses)
    _apply_losses(target_city, defender_losses)

    db.add(attacker_city)
    db.add(target_city)

    attacker_remaining = {
        unit: max(0, amount - attacker_losses.get(unit, 0)) for unit, amount in troops_sent.items()
    }
    defender_remaining = {
        unit: max(0, amount - defender_losses.get(unit, 0)) for unit, amount in defender_troops.items()
    }
    attacker_strength = _calculate_strength(attacker_remaining)
    defender_strength = _calculate_strength(defender_remaining)
    victory = attacker_strength >= defender_strength

    conquered = False
    if victory and troops_sent.get("noble", 0) > 0:
        target_city.loyalty = max(0.0, target_city.loyalty - LOYALTY_DROP_PER_SUCCESS)
        if target_city.loyalty <= 0:
            target_city.owner_id = attacker_city.owner_id
            target_city.loyalty = 100.0
            conquered = True

    db.commit()
    db.refresh(attacker_city)
    db.refresh(target_city)
    return victory, conquered


def found_city(
    db: Session, owner: models.User, origin_city: models.City, name: str, x: int, y: int
) -> models.City:
    production.recalculate_resources(db, origin_city)
    existing_city = db.query(models.City).filter(models.City.x == x, models.City.y == y).first()
    if existing_city:
        raise ValueError("Another city already exists at those coordinates")

    for resource, amount in FOUNDING_COST.items():
        if getattr(origin_city, resource) < amount:
            raise ValueError("Not enough resources to found a new city")
    production.pay_cost(origin_city, FOUNDING_COST)

    tile_type = world_gen.get_tile_type(x, y)
    new_city = models.City(name=name, x=x, y=y, owner_id=owner.id, loyalty=100.0, tile_type=tile_type)
    db.add(new_city)
    db.commit()
    db.refresh(new_city)

    for building in STARTER_BUILDINGS:
        starter = models.Building(city_id=new_city.id, name=building["name"], level=building["level"])
        db.add(starter)
    db.commit()
    db.refresh(new_city)
    return new_city

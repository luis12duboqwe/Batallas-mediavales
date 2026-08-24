"""Authoritative troop upkeep accounting for BM-0063.

Upkeep is denominated in the canonical gold resource. Committed troops keep
costing upkeep while they are away from their home city; queued training
reserves future upkeep so concurrent training cannot overbook the city's
sustainable military economy.

Temporary production events are intentionally excluded from the sustainable
capacity calculation. A short event may improve the current net gold flow, but
must not permanently authorize an army that the settlement cannot normally
maintain once the event ends.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models
from . import balance

UPKEEP_RESOURCE = "gold"


def unit_upkeep_per_hour(unit_type: str, quantity: int = 1) -> float:
    """Return canonical hourly upkeep for ``quantity`` units."""

    definition = balance.UNIT_CATALOG.get(unit_type)
    if definition is None:
        raise ValueError(f"Unknown unit type: {unit_type}")
    amount = int(quantity)
    if amount < 0:
        raise ValueError("Unit quantity cannot be negative")
    return float(definition.get("upkeep_per_hour", 0.0)) * amount


def _movement_upkeep(movement: models.Movement) -> float:
    """Return upkeep carried by one ongoing military movement."""

    if movement.movement_type == "spy":
        return unit_upkeep_per_hour("spy", int(movement.spy_count or 0))
    return sum(
        unit_upkeep_per_hour(unit_type, int(quantity))
        for unit_type, quantity in (movement.troops or {}).items()
        if int(quantity) > 0
    )


def get_committed_upkeep_per_hour(db: Session, city: models.City) -> float:
    """Return upkeep of all troops currently committed to this city.

    Dispatch removes troops from the city's ``troops`` rows, so outgoing armies
    and return marches must be counted explicitly. This mirrors population
    accounting and prevents sending an army away from making its upkeep vanish.
    Reinforcements that have already arrived are represented as troops in the
    receiving city by the current movement lifecycle and therefore naturally
    move to that city's upkeep account.
    """

    home_troops = (
        db.query(models.Troop)
        .filter(models.Troop.city_id == city.id)
        .all()
    )
    total = sum(
        unit_upkeep_per_hour(troop.unit_type, int(troop.quantity))
        for troop in home_troops
        if int(troop.quantity) > 0
    )

    outgoing = (
        db.query(models.Movement)
        .filter(
            models.Movement.origin_city_id == city.id,
            models.Movement.status == "ongoing",
            models.Movement.movement_type.in_(["attack", "spy", "reinforce"]),
        )
        .all()
    )
    total += sum(_movement_upkeep(movement) for movement in outgoing)

    returning = (
        db.query(models.Movement)
        .filter(
            models.Movement.target_city_id == city.id,
            models.Movement.status == "ongoing",
            models.Movement.movement_type == "return",
        )
        .all()
    )
    total += sum(_movement_upkeep(movement) for movement in returning)
    return float(total)


def get_reserved_upkeep_per_hour(db: Session, city_id: int) -> float:
    """Return future upkeep reserved by active troop-training queues."""

    queues = (
        db.query(models.TroopQueue)
        .filter(models.TroopQueue.city_id == city_id)
        .all()
    )
    return float(
        sum(
            unit_upkeep_per_hour(queue.troop_type, int(queue.amount))
            for queue in queues
            if int(queue.amount) > 0
        )
    )


def get_stable_upkeep_capacity_per_hour(db: Session, city: models.City) -> float:
    """Return permanent hourly gold income available to sustain troops.

    The capacity includes world rules, settlement type and permanent owned gold
    oasis bonuses, but deliberately excludes temporary world-event modifiers.
    """

    world = city.world
    if world is None:
        world = db.query(models.World).filter(models.World.id == city.world_id).one()

    world_modifier = max(float(world.resource_modifier or 0.0), 0.0)
    settlement_multiplier = (
        balance.CAMP_PRODUCTION_MULTIPLIER
        if getattr(city, "settlement_type", "city") == "camp"
        else 1.0
    )
    gold_oasis_bonus = sum(
        max(float(oasis.bonus_percent or 0.0), 0.0) / 100.0
        for oasis in (
            db.query(models.Oasis)
            .filter(
                models.Oasis.owner_city_id == city.id,
                models.Oasis.resource_type == UPKEEP_RESOURCE,
            )
            .all()
        )
    )
    return float(
        balance.PRODUCTION_RATES_PER_HOUR[UPKEEP_RESOURCE]
        * world_modifier
        * settlement_multiplier
        * (1.0 + gold_oasis_bonus)
    )


def get_upkeep_status(db: Session, city: models.City) -> dict[str, float | bool]:
    """Return committed, reserved and sustainable upkeep headroom."""

    used = get_committed_upkeep_per_hour(db, city)
    reserved = get_reserved_upkeep_per_hour(db, city.id)
    capacity = get_stable_upkeep_capacity_per_hour(db, city)
    available = max(capacity - used - reserved, 0.0)
    return {
        "used_per_hour": used,
        "reserved_per_hour": reserved,
        "capacity_per_hour": capacity,
        "available_per_hour": available,
        "sustainable": used + reserved <= capacity + 1e-9,
    }


def can_reserve_upkeep(
    db: Session,
    city: models.City,
    unit_type: str,
    quantity: int,
) -> bool:
    """Return whether adding a training order stays within stable capacity."""

    projected = unit_upkeep_per_hour(unit_type, quantity)
    status = get_upkeep_status(db, city)
    return projected <= float(status["available_per_hour"]) + 1e-9

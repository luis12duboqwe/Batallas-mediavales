from datetime import timezone
from typing import Dict

from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import event as event_service

PRODUCTION_RATES = {
    "wood": 15.0,
    "clay": 12.0,
    "iron": 10.0,
}
RESOURCE_FIELDS = frozenset(PRODUCTION_RATES)

LOYALTY_RECOVERY_PER_HOUR = 2.0
BASE_STORAGE = 5000.0
STORAGE_PER_WAREHOUSE_LEVEL = 2000.0


def _ensure_timezone(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_storage_limit(city: models.City) -> float:
    """Return server-authoritative storage capacity for the city.

    A city always has the base capacity. Each completed ``warehouse`` level
    increases the capacity; unrelated buildings such as the town hall do not.
    """

    warehouse_level = 0
    for building in city.buildings or []:
        if building.name == "warehouse":
            warehouse_level = max(int(building.level), 0)
            break
    return BASE_STORAGE + STORAGE_PER_WAREHOUSE_LEVEL * warehouse_level


def get_production_per_hour(db: Session, city: models.City) -> Dict[str, float]:
    """Return resource rates expressed strictly in units per hour."""

    modifiers = event_service.get_active_modifiers(db)
    rate_multiplier = modifiers.get("production_speed", 1.0)
    world_modifier = city.world.resource_modifier if city.world else 1.0

    oasis_bonuses = {"wood": 0.0, "clay": 0.0, "iron": 0.0}
    oases = getattr(city, "oases", [])
    for oasis in oases:
        if oasis.resource_type in oasis_bonuses:
            oasis_bonuses[oasis.resource_type] += oasis.bonus_percent / 100.0

    total_multiplier = rate_multiplier * world_modifier

    production = {}
    for resource, rate in PRODUCTION_RATES.items():
        bonus = oasis_bonuses.get(resource, 0.0)
        production[resource] = rate * total_multiplier * (1.0 + bonus)

    return production


def lock_city_for_update(db: Session, city: models.City | int) -> models.City:
    """Reload and row-lock a city for an economic transaction.

    ``populate_existing`` is intentional: routers frequently pass a City that
    was loaded before the transaction begins. After waiting for another writer,
    the resource values must be refreshed from the committed database row before
    validating a spend.
    """

    city_id = city if isinstance(city, int) else city.id
    locked_city = (
        db.query(models.City)
        .filter(models.City.id == city_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if locked_city is None:
        raise ValueError("City not found")
    return locked_city


def recalculate_resources(
    db: Session,
    city: models.City,
    return_gains: bool = False,
    *,
    commit: bool = True,
) -> models.City | tuple[models.City, Dict[str, float]]:
    """Accrue passive resources from an hourly rate.

    ``commit=False`` is used inside larger economic transactions so callers can
    keep a PostgreSQL row lock until validation, payment and the domain record
    are committed together.
    """

    now = utc_now()
    last_prod = _ensure_timezone(city.last_production or now)
    elapsed_hours = max((now - last_prod).total_seconds() / 3600.0, 0.0)
    if elapsed_hours == 0:
        gains = {resource: 0.0 for resource in PRODUCTION_RATES}
        return (city, gains) if return_gains else city

    production_rates = get_production_per_hour(db, city)
    storage_limit = get_storage_limit(city)

    gains: Dict[str, float] = {}
    for resource, rate in production_rates.items():
        produced = rate * elapsed_hours
        current_value = float(getattr(city, resource))

        # Reaching storage stops future accumulation. If legacy/admin data is
        # already above the current cap, recalculation must not delete it.
        if current_value >= storage_limit:
            new_value = current_value
            actual_gain = 0.0
        else:
            new_value = min(current_value + produced, storage_limit)
            actual_gain = max(new_value - current_value, 0.0)

        gains[resource] = actual_gain
        setattr(city, resource, new_value)

    loyalty_gain = LOYALTY_RECOVERY_PER_HOUR * elapsed_hours
    city.loyalty = min(100.0, city.loyalty + loyalty_gain)

    # Always consume elapsed time, including while storage is full. Otherwise a
    # player could spend after being capped and receive an artificial backlog.
    city.last_production = now

    db.add(city)
    if commit:
        db.commit()
        db.refresh(city)
        record_resource_gains(db, city, gains)
    else:
        db.flush()

    return (city, gains) if return_gains else city


def lock_and_recalculate_resources(
    db: Session, city: models.City | int
) -> tuple[models.City, Dict[str, float]]:
    """Acquire the city row lock and accrue production without releasing it."""

    locked_city = lock_city_for_update(db, city)
    locked_city, gains = recalculate_resources(
        db,
        locked_city,
        return_gains=True,
        commit=False,
    )
    return locked_city, gains


def record_resource_gains(
    db: Session, city: models.City, gains: Dict[str, float]
) -> None:
    """Record achievement progress after the enclosing transaction commits."""

    generated_total = sum(max(float(value), 0.0) for value in gains.values())
    if generated_total <= 0 or not city.owner_id:
        return

    from .achievement import update_achievement_progress

    update_achievement_progress(
        db,
        city.owner_id,
        "resources_collected",
        increment=int(generated_total),
    )


def _validate_cost(cost: Dict[str, float]) -> None:
    for resource, amount in cost.items():
        if resource not in RESOURCE_FIELDS:
            raise ValueError(f"Unknown resource: {resource}")
        if amount < 0:
            raise ValueError("Resource costs cannot be negative")


def check_cost(city: models.City, cost: Dict[str, float]) -> bool:
    """Check if the city has enough resources to pay the cost."""

    _validate_cost(cost)
    return all(getattr(city, resource) >= amount for resource, amount in cost.items())


def pay_cost(city: models.City, cost: Dict[str, float]):
    """Deduct resources from a row-locked city without allowing negatives."""

    if not check_cost(city, cost):
        raise ValueError("Insufficient resources")

    for resource, amount in cost.items():
        new_value = getattr(city, resource) - amount
        if new_value < 0:
            raise ValueError("Resource balance cannot become negative")
        setattr(city, resource, new_value)

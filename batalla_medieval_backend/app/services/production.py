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

LOYALTY_RECOVERY_PER_HOUR = 2.0
BASE_STORAGE = 5000.0
STORAGE_PER_LEVEL = 2000.0


def _ensure_timezone(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_storage_limit(city: models.City) -> float:
    """Capacidad de almacén derivada del nivel de ayuntamiento."""

    level = 1
    for building in city.buildings or []:
        if building.name == "town_hall":
            level = max(building.level, level)
            break
    return BASE_STORAGE + STORAGE_PER_LEVEL * max(level - 1, 0)


def get_production_per_hour(db: Session, city: models.City) -> Dict[str, float]:
    modifiers = event_service.get_active_modifiers(db)
    rate_multiplier = modifiers.get("production_speed", 1.0)
    world_modifier = city.world.resource_modifier if city.world else 1.0
    
    # Calculate oasis bonuses
    oasis_bonuses = {"wood": 0.0, "clay": 0.0, "iron": 0.0}
    # Use getattr to avoid error if oases relationship is not loaded or defined (though it should be)
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


def recalculate_resources(
    db: Session, city: models.City, return_gains: bool = False
) -> models.City | tuple[models.City, Dict[str, float]]:
    now = utc_now()
    last_prod = _ensure_timezone(city.last_production or now)
    elapsed_minutes = max((now - last_prod).total_seconds() / 60, 0)
    if elapsed_minutes == 0:
        gains = {resource: 0.0 for resource in PRODUCTION_RATES}
        return (city, gains) if return_gains else city

    production_rates = get_production_per_hour(db, city)
    storage_limit = get_storage_limit(city)

    gains: Dict[str, float] = {}
    generated_total = 0.0
    for resource, rate in production_rates.items():
        produced = rate * elapsed_minutes
        current_value = getattr(city, resource)
        new_value = min(current_value + produced, storage_limit)
        actual_gain = max(new_value - current_value, 0)
        gains[resource] = actual_gain
        generated_total += actual_gain
        setattr(city, resource, new_value)

    loyalty_gain = LOYALTY_RECOVERY_PER_HOUR * (elapsed_minutes / 60)
    city.loyalty = min(100.0, city.loyalty + loyalty_gain)
    city.last_production = now

    db.add(city)
    db.commit()
    db.refresh(city)

    if generated_total > 0 and city.owner_id:
        from .achievement import update_achievement_progress

        update_achievement_progress(
            db,
            city.owner_id,
            "resources_collected",
            increment=int(generated_total),
        )

    return (city, gains) if return_gains else city


def check_cost(city: models.City, cost: Dict[str, float]) -> bool:
    """Check if the city has enough resources to pay the cost."""
    for resource, amount in cost.items():
        if getattr(city, resource) < amount:
            return False
    return True


def pay_cost(city: models.City, cost: Dict[str, float]):
    """Deduct resources from the city. Raises ValueError if insufficient."""
    if not check_cost(city, cost):
        raise ValueError("Insufficient resources")
    
    for resource, amount in cost.items():
        setattr(city, resource, getattr(city, resource) - amount)

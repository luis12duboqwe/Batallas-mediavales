from datetime import timezone
from typing import Dict

from sqlalchemy import update
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import balance, event as event_service, hero_rules, upkeep as upkeep_service

# Compatibility aliases. The objects and values are owned by ``balance``.
PRODUCTION_RATES = balance.PRODUCTION_RATES_PER_HOUR
RESOURCE_FIELDS = frozenset(balance.RESOURCE_FIELDS)
LOYALTY_RECOVERY_PER_HOUR = balance.LOYALTY_RECOVERY_PER_HOUR
BASE_STORAGE = balance.STORAGE_BASE_CAPACITY
STORAGE_PER_WAREHOUSE_LEVEL = balance.STORAGE_PER_WAREHOUSE_LEVEL
_RECALCULATION_RETRIES = 5


def _ensure_timezone(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_storage_limit(city: models.City) -> float:
    """Return server-authoritative storage capacity for the settlement."""

    warehouse_level = 0
    for building in city.buildings or []:
        if building.name == "warehouse":
            warehouse_level = max(int(building.level), 0)
            break
    return balance.get_storage_capacity(warehouse_level)


def _production_hero(db: Session, city: models.City) -> models.Hero | None:
    if not city.owner_id or getattr(city, "settlement_type", "city") != "city":
        return None
    return (
        db.query(models.Hero)
        .filter(
            models.Hero.user_id == city.owner_id,
            models.Hero.world_id == city.world_id,
            models.Hero.city_id == city.id,
            models.Hero.status == "home",
            models.Hero.health > 0,
        )
        .one_or_none()
    )


def get_gross_production_per_hour(db: Session, city: models.City) -> Dict[str, float]:
    """Return resource income before troop upkeep, in units per hour.

    BM-0068 adds the home hero's bounded production attribute to the existing
    event/world/settlement/oasis calculation. The bonus is additive with oasis
    percentages and disappears while the hero is away, dead, or assigned to a
    different city/world.
    """

    modifiers = event_service.get_active_modifiers(db, world_id=city.world_id)
    rate_multiplier = modifiers.get("production_speed", 1.0)
    world_modifier = city.world.resource_modifier if city.world else 1.0
    settlement_multiplier = (
        balance.CAMP_PRODUCTION_MULTIPLIER
        if getattr(city, "settlement_type", "city") == "camp"
        else 1.0
    )

    oasis_bonuses = {resource: 0.0 for resource in balance.RESOURCE_FIELDS}
    oases = getattr(city, "oases", [])
    for oasis in oases:
        if oasis.resource_type in oasis_bonuses:
            oasis_bonuses[oasis.resource_type] += oasis.bonus_percent / 100.0

    hero_bonus = hero_rules.production_bonus(_production_hero(db, city))
    total_multiplier = rate_multiplier * world_modifier * settlement_multiplier

    production = {}
    for resource, rate in PRODUCTION_RATES.items():
        oasis_bonus = oasis_bonuses.get(resource, 0.0)
        production[resource] = rate * total_multiplier * (1.0 + oasis_bonus + hero_bonus)

    return production


def get_production_per_hour(db: Session, city: models.City) -> Dict[str, float]:
    """Return net resource rates after committed troop upkeep.

    Upkeep is paid only in gold and follows troops while they are deployed or
    returning. Training queues reserve future upkeep for admission control but
    do not consume gold until their troops actually finish training.
    """

    production = get_gross_production_per_hour(db, city)
    production[upkeep_service.UPKEEP_RESOURCE] -= (
        upkeep_service.get_committed_upkeep_per_hour(db, city)
    )
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


def _calculate_recalculation(
    db: Session,
    city: models.City,
    now,
) -> tuple[dict[str, float], dict[str, float], float, float]:
    """Calculate one production tick without mutating the mapped City row."""

    last_prod = _ensure_timezone(city.last_production or now)
    elapsed_hours = max((now - last_prod).total_seconds() / 3600.0, 0.0)
    if elapsed_hours == 0:
        return (
            {resource: float(getattr(city, resource)) for resource in PRODUCTION_RATES},
            {resource: 0.0 for resource in PRODUCTION_RATES},
            float(city.loyalty),
            0.0,
        )

    production_rates = get_production_per_hour(db, city)
    storage_limit = get_storage_limit(city)
    new_resources: dict[str, float] = {}
    gains: Dict[str, float] = {}

    for resource, rate in production_rates.items():
        produced = rate * elapsed_hours
        current_value = float(getattr(city, resource))

        if produced >= 0:
            if current_value >= storage_limit:
                new_value = current_value
                actual_gain = 0.0
            else:
                new_value = min(current_value + produced, storage_limit)
                actual_gain = max(new_value - current_value, 0.0)
        else:
            new_value = max(current_value + produced, 0.0)
            actual_gain = 0.0

        new_resources[resource] = new_value
        gains[resource] = actual_gain

    loyalty_gain = LOYALTY_RECOVERY_PER_HOUR * elapsed_hours
    new_loyalty = min(100.0, float(city.loyalty) + loyalty_gain)
    return new_resources, gains, new_loyalty, elapsed_hours


def _apply_recalculation(
    city: models.City,
    new_resources: dict[str, float],
    new_loyalty: float,
    now,
) -> None:
    for resource, value in new_resources.items():
        setattr(city, resource, value)
    city.loyalty = new_loyalty
    city.last_production = now


def _same_timestamp_condition(column, value):
    return column.is_(None) if value is None else column == value


def _commit_recalculation_safely(
    db: Session,
    city: models.City,
    return_gains: bool,
):
    """Commit a lazy production tick without allowing stale-read lost updates.

    PostgreSQL serializes on ``FOR UPDATE``. SQLite ignores that clause, and a
    browser can have overlapping GET requests that loaded the city before an
    economic POST committed. The compare-and-swap predicate below additionally
    verifies every resource balance, loyalty and ``last_production`` observed by
    the tick. If another transaction pays a cost or otherwise advances the city,
    the stale UPDATE affects zero rows, is rolled back, reloads the latest state
    and retries instead of restoring the old balance.
    """

    city_id = city.id
    for _ in range(_RECALCULATION_RETRIES):
        locked_city = lock_city_for_update(db, city_id)
        baseline_resources = {
            resource: float(getattr(locked_city, resource))
            for resource in PRODUCTION_RATES
        }
        baseline_loyalty = float(locked_city.loyalty)
        baseline_last_production = locked_city.last_production
        now = utc_now()
        new_resources, gains, new_loyalty, elapsed_hours = _calculate_recalculation(
            db, locked_city, now
        )

        if elapsed_hours == 0:
            db.commit()
            db.refresh(locked_city)
            return (locked_city, gains) if return_gains else locked_city

        conditions = [
            models.City.id == city_id,
            models.City.loyalty == baseline_loyalty,
            _same_timestamp_condition(
                models.City.last_production, baseline_last_production
            ),
        ]
        conditions.extend(
            getattr(models.City, resource) == baseline_resources[resource]
            for resource in PRODUCTION_RATES
        )
        values = {
            **new_resources,
            "loyalty": new_loyalty,
            "last_production": now,
        }

        with db.no_autoflush:
            result = db.execute(
                update(models.City)
                .where(*conditions)
                .values(**values)
                .execution_options(synchronize_session=False)
            )

        if result.rowcount == 1:
            db.commit()
            db.refresh(locked_city)
            record_resource_gains(db, locked_city, gains)
            return (locked_city, gains) if return_gains else locked_city

        db.rollback()
        db.expire_all()

    raise RuntimeError("Could not recalculate city resources after concurrent updates")


def recalculate_resources(
    db: Session,
    city: models.City,
    return_gains: bool = False,
    *,
    commit: bool = True,
) -> models.City | tuple[models.City, Dict[str, float]]:
    """Accrue passive resources and continuously pay troop upkeep.

    Positive production remains capped by storage. Net gold may become negative
    when an existing army is no longer economically sustainable (for example,
    after losing a gold oasis); in that case gold drains to zero but never
    becomes debt. The elapsed interval is still consumed, preventing backlog
    exploits when resources are capped or depleted.

    ``commit=False`` is used inside larger economic transactions so callers can
    keep a PostgreSQL row lock until validation, payment and the domain record
    are committed together. Committing lazy/read-side ticks use an optimistic
    compare-and-swap in addition to the row lock so SQLite/browser concurrency
    cannot restore a stale resource snapshot over a just-committed spend.
    """

    if commit:
        return _commit_recalculation_safely(db, city, return_gains)

    now = utc_now()
    new_resources, gains, new_loyalty, elapsed_hours = _calculate_recalculation(
        db, city, now
    )
    if elapsed_hours == 0:
        return (city, gains) if return_gains else city

    _apply_recalculation(city, new_resources, new_loyalty, now)
    db.add(city)
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
        world_id=city.world_id,
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

"""Server-authoritative territorial expansion for BM-0061."""

from __future__ import annotations

import logging
from copy import deepcopy

from sqlalchemy.orm import Session

from .. import models
from . import balance, production, world_gen

logger = logging.getLogger(__name__)

SETTLEMENT_TYPES = ("city", "camp")


def _lock_membership(db: Session, *, user_id: int, world_id: int) -> models.PlayerWorld:
    membership = (
        db.query(models.PlayerWorld)
        .filter(
            models.PlayerWorld.user_id == user_id,
            models.PlayerWorld.world_id == world_id,
        )
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if membership is None:
        raise ValueError("Player has not joined this world")
    return membership


def _lock_active_world(db: Session, world_id: int) -> models.World:
    world = (
        db.query(models.World)
        .filter(models.World.id == world_id, models.World.is_active.is_(True))
        .with_for_update()
        .one_or_none()
    )
    if world is None:
        raise ValueError("World not found or inactive")
    return world


def _validate_origin(owner: models.User, origin: models.City, world_id: int) -> None:
    if origin.owner_id != owner.id:
        raise ValueError("Origin settlement does not belong to player")
    if origin.world_id != world_id:
        raise ValueError("Cross-world expansion is not allowed")
    if origin.settlement_type != "city":
        raise ValueError("Only a full city can found another settlement")


def _validate_coordinates(
    db: Session,
    *,
    world: models.World,
    x: int,
    y: int,
) -> str:
    if x < 0 or y < 0 or x >= int(world.map_size) or y >= int(world.map_size):
        raise ValueError("Invalid coordinates for this world")

    tile_type = world_gen.get_tile_type(x, y)
    if tile_type == "water":
        raise ValueError("Settlements cannot be founded on water")

    city_exists = (
        db.query(models.City.id)
        .filter(
            models.City.world_id == world.id,
            models.City.x == x,
            models.City.y == y,
        )
        .first()
        is not None
    )
    if city_exists:
        raise ValueError("Another settlement already exists at those coordinates")

    oasis_exists = (
        db.query(models.Oasis.id)
        .filter(
            models.Oasis.world_id == world.id,
            models.Oasis.x == x,
            models.Oasis.y == y,
        )
        .first()
        is not None
    )
    if oasis_exists:
        raise ValueError("An oasis already occupies those coordinates")

    return tile_type


def _consume_expansion_points(membership: models.PlayerWorld, amount: int) -> None:
    if amount < 0:
        raise ValueError("Expansion point cost cannot be negative")
    current = int(membership.expansion_points or 0)
    if current < amount:
        raise ValueError("Not enough expansion points")
    membership.expansion_points = current - amount


def _create_starter_buildings(
    db: Session,
    settlement: models.City,
    definitions,
) -> None:
    for definition in definitions:
        db.add(
            models.Building(
                city_id=settlement.id,
                name=definition["name"],
                level=int(definition["level"]),
            )
        )


def award_expansion_points_for_building(
    db: Session,
    city: models.City,
    building_name: str,
) -> int:
    """Mint points inside the same transaction that completes the building queue."""

    amount = int(balance.EXPANSION_POINTS_PER_COMPLETION.get(building_name, 0))
    if amount <= 0 or city.owner_id is None or city.settlement_type != "city":
        return 0

    membership = (
        db.query(models.PlayerWorld)
        .filter(
            models.PlayerWorld.user_id == city.owner_id,
            models.PlayerWorld.world_id == city.world_id,
        )
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if membership is None:
        logger.warning(
            "expansion_points_missing_membership",
            extra={"city_id": city.id, "owner_id": city.owner_id, "world_id": city.world_id},
        )
        return 0

    membership.expansion_points = int(membership.expansion_points or 0) + amount
    db.add(membership)
    db.flush()
    return amount


def get_expansion_status(
    db: Session,
    *,
    user_id: int,
    world_id: int,
) -> dict:
    membership = (
        db.query(models.PlayerWorld)
        .filter(
            models.PlayerWorld.user_id == user_id,
            models.PlayerWorld.world_id == world_id,
        )
        .one_or_none()
    )
    if membership is None:
        raise ValueError("Player has not joined this world")

    owned = (
        db.query(models.City)
        .filter(
            models.City.owner_id == user_id,
            models.City.world_id == world_id,
        )
        .all()
    )
    return {
        "world_id": world_id,
        "expansion_points": int(membership.expansion_points or 0),
        "city_count": sum(1 for settlement in owned if settlement.settlement_type == "city"),
        "camp_count": sum(1 for settlement in owned if settlement.settlement_type == "camp"),
        "point_costs": deepcopy(balance.SETTLEMENT_EXPANSION_POINT_COSTS),
        "camp_promotion_point_cost": balance.CAMP_PROMOTION_POINT_COST,
        "city_founding_cost": deepcopy(balance.CITY_FOUNDING_COST),
        "camp_founding_cost": deepcopy(balance.CAMP_FOUNDING_COST),
        "camp_promotion_cost": deepcopy(balance.CAMP_PROMOTION_COST),
        "points_per_completion": deepcopy(balance.EXPANSION_POINTS_PER_COMPLETION),
    }


def found_settlement(
    db: Session,
    owner: models.User,
    origin_city: models.City,
    name: str,
    x: int,
    y: int,
    settlement_type: str,
) -> models.City:
    """Consume world-scoped points/resources and create one settlement atomically."""

    if settlement_type not in SETTLEMENT_TYPES:
        raise ValueError("Unknown settlement type")
    cleaned_name = name.strip()
    if not cleaned_name or len(cleaned_name) > 100:
        raise ValueError("Settlement name must contain 1 to 100 characters")

    try:
        membership = _lock_membership(
            db,
            user_id=owner.id,
            world_id=origin_city.world_id,
        )
        world = _lock_active_world(db, origin_city.world_id)
        origin_city, production_gains = production.lock_and_recalculate_resources(
            db, origin_city
        )
        _validate_origin(owner, origin_city, world.id)
        tile_type = _validate_coordinates(db, world=world, x=x, y=y)

        point_cost = int(balance.SETTLEMENT_EXPANSION_POINT_COSTS[settlement_type])
        resource_cost = (
            balance.CITY_FOUNDING_COST
            if settlement_type == "city"
            else balance.CAMP_FOUNDING_COST
        )
        _consume_expansion_points(membership, point_cost)
        if not production.check_cost(origin_city, resource_cost):
            raise ValueError("Not enough resources to found settlement")
        production.pay_cost(origin_city, resource_cost)

        starting_resources = (
            balance.CITY_STARTING_RESOURCES
            if settlement_type == "city"
            else balance.CAMP_STARTING_RESOURCES
        )
        settlement = models.City(
            name=cleaned_name,
            x=x,
            y=y,
            owner_id=owner.id,
            world_id=world.id,
            settlement_type=settlement_type,
            loyalty=balance.CITY_INITIAL_LOYALTY,
            population_max=(
                balance.CITY_POPULATION_MAX
                if settlement_type == "city"
                else balance.CAMP_POPULATION_MAX
            ),
            tile_type=tile_type,
            **{
                resource: float(starting_resources[resource])
                for resource in balance.RESOURCE_FIELDS
            },
        )
        db.add(settlement)
        db.flush()
        _create_starter_buildings(
            db,
            settlement,
            balance.STARTER_BUILDINGS
            if settlement_type == "city"
            else balance.CAMP_STARTER_BUILDINGS,
        )
        db.add(membership)
        db.add(origin_city)
        db.commit()
        db.refresh(settlement)
        production.record_resource_gains(db, origin_city, production_gains)
        return settlement
    except Exception:
        db.rollback()
        raise


def promote_camp(
    db: Session,
    owner: models.User,
    camp: models.City,
) -> models.City:
    """Promote a camp by paying exactly the remaining city cost and point cost."""

    try:
        membership = _lock_membership(
            db,
            user_id=owner.id,
            world_id=camp.world_id,
        )
        camp, production_gains = production.lock_and_recalculate_resources(db, camp)
        if camp.owner_id != owner.id:
            raise ValueError("Camp does not belong to player")
        if camp.settlement_type != "camp":
            raise ValueError("Only camps can be promoted")

        _consume_expansion_points(membership, balance.CAMP_PROMOTION_POINT_COST)
        if not production.check_cost(camp, balance.CAMP_PROMOTION_COST):
            raise ValueError("Not enough resources to promote camp")
        production.pay_cost(camp, balance.CAMP_PROMOTION_COST)

        camp.settlement_type = "city"
        camp.population_max = max(int(camp.population_max), balance.CITY_POPULATION_MAX)

        town_hall = (
            db.query(models.Building)
            .filter(
                models.Building.city_id == camp.id,
                models.Building.name == "town_hall",
            )
            .one_or_none()
        )
        if town_hall is None:
            db.add(models.Building(city_id=camp.id, name="town_hall", level=1))
        elif town_hall.level < 1:
            town_hall.level = 1

        db.add(membership)
        db.add(camp)
        db.commit()
        db.refresh(camp)
        production.record_resource_gains(db, camp, production_gains)
        return camp
    except Exception:
        db.rollback()
        raise

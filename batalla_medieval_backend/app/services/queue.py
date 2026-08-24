"""Helpers to process building, research, troop, and movement queues."""

import logging

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..utils import utc_now
from . import (
    building,
    movement,
    notification as notification_service,
    production,
    research,
    troops,
)

logger = logging.getLogger(__name__)


def _city_with_owner(db: Session, city_id: int):
    return (
        db.query(models.City)
        .options(selectinload(models.City.owner))
        .filter(models.City.id == city_id)
        .first()
    )


def _settle_due_military_economy(db: Session) -> list[tuple[int, dict[str, float]]]:
    """Accrue production/upkeep before due military state transitions.

    A completed training queue starts consuming upkeep only after completion.
    Likewise combat/spy losses or an arriving reinforcement must not change the
    upkeep rate retroactively for the elapsed interval before the worker handles
    that transition. We therefore lock every affected city in stable id order
    and advance its resource clock using the pre-transition troop/movement state.

    The enclosing movement resolver commits these settlements together with the
    military mutations. Returned gains are recorded only after that commit.
    """

    now = utc_now()
    due_training_city_ids = {
        city_id
        for (city_id,) in (
            db.query(models.TroopQueue.city_id)
            .filter(models.TroopQueue.finish_time <= now)
            .all()
        )
    }
    due_movements = (
        db.query(models.Movement.origin_city_id, models.Movement.target_city_id)
        .filter(
            models.Movement.arrival_time <= now,
            models.Movement.status == "ongoing",
        )
        .all()
    )
    city_ids = set(due_training_city_ids)
    for origin_city_id, target_city_id in due_movements:
        if origin_city_id is not None:
            city_ids.add(origin_city_id)
        if target_city_id is not None:
            city_ids.add(target_city_id)

    settlements: list[tuple[int, dict[str, float]]] = []
    for city_id in sorted(city_ids):
        city = (
            db.query(models.City)
            .filter(models.City.id == city_id)
            .with_for_update()
            .populate_existing()
            .one_or_none()
        )
        if city is None:
            continue
        city, gains = production.recalculate_resources(
            db,
            city,
            return_gains=True,
            commit=False,
        )
        settlements.append((city.id, gains))
    return settlements


def _record_settled_resource_gains(
    db: Session, settlements: list[tuple[int, dict[str, float]]]
) -> None:
    """Record passive gains after the military transaction has committed."""

    for city_id, gains in settlements:
        city = db.query(models.City).filter(models.City.id == city_id).one_or_none()
        if city is not None:
            production.record_resource_gains(db, city, gains)


def process_all_queues(db: Session) -> dict:
    """Process all queue types and send completion notifications."""

    finished_buildings = building.process_building_queues(db)
    finished_research = research.process_research_queues(db)

    # Settle the economic clock before troop completion, battle losses, spy
    # losses, reinforcement arrival or any other due movement changes which
    # units are responsible for upkeep. The city locks remain held until the
    # military processors commit.
    military_settlements = _settle_due_military_economy(db)
    finished_troops = troops.process_troop_queues(db)
    finished_movements = movement.resolve_due_movements(db)
    _record_settled_resource_gains(db, military_settlements)

    for finished in finished_buildings:
        city = _city_with_owner(db, finished["city_id"])
        if city and city.owner:
            notification_service.create_notification(
                db,
                city.owner,
                title="Construcción completada",
                body=f"Tu edificio {finished['building_type']} ha alcanzado el nivel {finished['target_level']}",
                notification_type="building_complete",
            )

    for finished in finished_research:
        city = _city_with_owner(db, finished["city_id"])
        if city and city.owner:
            notification_service.create_notification(
                db,
                city.owner,
                title="Investigación completada",
                body=f"La tecnología {finished['tech_name']} ya está disponible en {city.name}.",
                notification_type="research_complete",
                allow_email=False,
            )

    for finished in finished_troops:
        city = _city_with_owner(db, finished["city_id"])
        if city and city.owner:
            notification_service.create_notification(
                db,
                city.owner,
                title="Entrenamiento completado",
                body=(
                    f"Se han entrenado {finished['amount']} unidades de {finished['troop_type']} en {city.name}."
                ),
                notification_type="troop_trained",
                allow_email=False,
            )

    logger.info(
        "queues_processed",
        extra={
            "buildings": len(finished_buildings),
            "research": len(finished_research),
            "troops": len(finished_troops),
            "movements": len(finished_movements),
        },
    )
    return {
        "buildings": finished_buildings,
        "research": finished_research,
        "troops": finished_troops,
        "movements": finished_movements,
    }


def get_active_queues_for_user(
    db: Session,
    user: models.User,
    world_id: int | None = None,
) -> dict:
    """Return all active queues owned by a user, optionally scoped to a world."""

    building_query = (
        db.query(models.BuildingQueue)
        .join(models.City, models.BuildingQueue.city_id == models.City.id)
        .filter(models.City.owner_id == user.id)
    )
    research_query = (
        db.query(models.ResearchQueue)
        .join(models.City, models.ResearchQueue.city_id == models.City.id)
        .filter(models.City.owner_id == user.id)
    )
    troop_query = (
        db.query(models.TroopQueue)
        .join(models.City, models.TroopQueue.city_id == models.City.id)
        .filter(models.City.owner_id == user.id)
    )
    movement_query = (
        db.query(models.Movement)
        .join(models.City, models.Movement.origin_city_id == models.City.id)
        .filter(models.City.owner_id == user.id, models.Movement.status == "ongoing")
    )

    if world_id is not None:
        building_query = building_query.filter(models.City.world_id == world_id)
        research_query = research_query.filter(models.City.world_id == world_id)
        troop_query = troop_query.filter(models.City.world_id == world_id)
        movement_query = movement_query.filter(models.City.world_id == world_id)

    return {
        "building_queues": building_query.all(),
        "research_queues": research_query.all(),
        "troop_queues": troop_query.all(),
        "movements": movement_query.all(),
    }

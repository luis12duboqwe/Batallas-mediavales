"""Helpers to process building, research, troop, and movement queues."""

import logging

from sqlalchemy.orm import Session, selectinload

from .. import models
from . import building, movement, notification as notification_service, research, troops

logger = logging.getLogger(__name__)


def _city_with_owner(db: Session, city_id: int):
    return (
        db.query(models.City)
        .options(selectinload(models.City.owner))
        .filter(models.City.id == city_id)
        .first()
    )


def process_all_queues(db: Session) -> dict:
    """Process all queue types and send completion notifications."""

    finished_buildings = building.process_building_queues(db)
    finished_research = research.process_research_queues(db)
    finished_troops = troops.process_troop_queues(db)
    finished_movements = movement.resolve_due_movements(db)

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

from sqlalchemy.orm import Session

from .. import models
from . import building, movement, notification as notification_service, troops


def process_all_queues(db: Session) -> dict:
    finished_buildings = building.process_building_queues(db)
    finished_troops = troops.process_troop_queues(db)
    finished_movements = movement.process_movements(db)

    for finished in finished_buildings:
        city = db.query(models.City).filter(models.City.id == finished["city_id"]).first()
        if city and city.owner:
            notification_service.create_notification(
                db,
                city.owner,
                title="Construcción completada",
                body=f"Tu edificio {finished['building_type']} ha alcanzado el nivel {finished['target_level']}",
                notification_type="building_complete",
            )

    for finished in finished_troops:
        city = db.query(models.City).filter(models.City.id == finished["city_id"]).first()
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

    return {
        "buildings": finished_buildings,
        "troops": finished_troops,
        "movements": finished_movements,
    }


def get_active_queues_for_user(db: Session, user: models.User) -> dict:
    building_queues = (
        db.query(models.BuildingQueue)
        .join(models.City, models.BuildingQueue.city_id == models.City.id)
        .filter(models.City.owner_id == user.id)
        .all()
    )
    troop_queues = (
        db.query(models.TroopQueue)
        .join(models.City, models.TroopQueue.city_id == models.City.id)
        .filter(models.City.owner_id == user.id)
        .all()
    )
    movements = (
        db.query(models.Movement)
        .join(models.City, models.Movement.origin_city_id == models.City.id)
        .filter(models.City.owner_id == user.id, models.Movement.status == "ongoing")
        .all()
    )
    return {
        "building_queues": building_queues,
        "troop_queues": troop_queues,
        "movements": movements,
    }

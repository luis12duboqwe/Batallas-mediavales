from sqlalchemy.orm import Session

from .. import models
from . import building, movement, troops


def process_all_queues(db: Session) -> dict:
    finished_buildings = building.process_building_queues(db)
    finished_troops = troops.process_troop_queues(db)
    finished_movements = movement.process_movements(db)

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

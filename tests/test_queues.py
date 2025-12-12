from datetime import datetime, timezone, timedelta

from app import models
from app.services import building, troops


def test_process_all_queues_finishes(db_session, city):
    city.wood = city.clay = city.iron = 5000
    # Add barracks for requirements
    barracks = models.Building(city_id=city.id, name="barracks", level=1)
    db_session.add(barracks)
    db_session.commit()

    building.queue_upgrade(db_session, city, "barracks")
    troop_queue = troops.queue_training(db_session, city, "basic_infantry", 2)

    db_session.query(models.BuildingQueue).update({models.BuildingQueue.finish_time: datetime.now(timezone.utc) - timedelta(seconds=1)})
    troop_queue.finish_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    finished_buildings = building.process_building_queues(db_session)
    finished_troops = troops.process_troop_queues(db_session)

    assert finished_buildings and finished_troops

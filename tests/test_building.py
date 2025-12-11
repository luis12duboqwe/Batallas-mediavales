from datetime import datetime, timedelta

from app import models
from app.services import building


def test_building_upgrade_and_completion(db_session, city):
    city.wood = city.clay = city.iron = 1000
    db_session.commit()

    result = building.queue_upgrade(db_session, city, "town_hall")
    assert isinstance(result, models.Building)
    queue = db_session.query(models.BuildingQueue).first()
    assert queue.target_level == 1

    queue.finish_time = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    finished = building.process_building_queues(db_session)
    assert finished[0]["target_level"] == 1

    updated_building = db_session.query(models.Building).filter_by(city_id=city.id, name="town_hall").first()
    assert updated_building.level == 1

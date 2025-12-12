from datetime import datetime, timezone, timedelta

from app import models
from app.services import troops


def test_troop_training_and_completion(db_session, city):
    city.wood = city.clay = city.iron = 5000
    # Add barracks
    barracks = models.Building(city_id=city.id, name="barracks", level=1)
    db_session.add(barracks)
    db_session.commit()

    queue_entry = troops.queue_training(db_session, city, "basic_infantry", 5)
    assert queue_entry.amount == 5

    queue_entry.finish_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    finished = troops.process_troop_queues(db_session)
    assert finished[0]["amount"] == 5

    troop_record = db_session.query(models.Troop).filter_by(city_id=city.id, unit_type="basic_infantry").first()
    assert troop_record.quantity == 5

from datetime import datetime, timezone

from app import models
from app.services import espionage


def test_spy_success_and_failure(monkeypatch, db_session, city, second_city):
    attacker_spies = models.Troop(city_id=city.id, unit_type="spy", quantity=5)
    defender_spies = models.Troop(city_id=second_city.id, unit_type="spy", quantity=2)
    db_session.add_all([attacker_spies, defender_spies])
    db_session.commit()

    def always_success():
        return 0.0

    monkeypatch.setattr(espionage.random, "random", always_success)
    movement = models.Movement(
        origin_city_id=city.id,
        target_city_id=second_city.id,
        world_id=city.world_id,
        movement_type="spy",
        spy_count=3,
        arrival_time=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(movement)
    db_session.commit()

    attacker_report, defender_report, _ = espionage.resolve_spy(db_session, movement)
    import json
    content = json.loads(attacker_report.content)
    assert content["success"] is True

    def always_fail():
        return 0.99

    monkeypatch.setattr(espionage.random, "random", always_fail)
    movement_fail = models.Movement(
        origin_city_id=city.id,
        target_city_id=second_city.id,
        world_id=city.world_id,
        movement_type="spy",
        spy_count=1,
        arrival_time=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(movement_fail)
    db_session.commit()

    attacker_report_fail, _, _ = espionage.resolve_spy(db_session, movement_fail)
    content_fail = json.loads(attacker_report_fail.content)
    assert content_fail["success"] is False

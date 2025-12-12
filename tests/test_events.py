from datetime import datetime, timezone, timedelta

from app import models
from app.services import event


def test_event_modifiers_and_creation(db_session):
    payload = models.WorldEvent(
        world_id=1,
        name="Doble de Recursos",
        description="",
        start_time=datetime.now(timezone.utc) - timedelta(hours=1),
        end_time=datetime.now(timezone.utc) + timedelta(hours=1),
        modifiers={"production_speed": 2.0},
    )
    db_session.add(payload)
    db_session.commit()

    modifiers = event.get_active_modifiers(db_session)
    assert modifiers["production_speed"] == 2.0

    merged = event._merge_modifiers({"movement_speed": 0.5})
    assert merged["movement_speed"] == 0.5

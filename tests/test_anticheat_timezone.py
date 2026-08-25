from datetime import timedelta, timezone

from app import models
from app.services import anticheat, movement
from app.utils import utc_now


def test_anticheat_normalizes_naive_and_aware_timestamps_to_utc():
    aware = utc_now()
    naive = aware.replace(tzinfo=None)

    normalized_aware = anticheat._as_utc(aware)
    normalized_naive = anticheat._as_utc(naive)

    assert normalized_aware.tzinfo == timezone.utc
    assert normalized_naive.tzinfo == timezone.utc
    assert normalized_naive == aware


def test_action_speed_accepts_sqlite_naive_last_action_timestamp(db_session, user):
    user.last_action_at = (utc_now() - timedelta(seconds=1)).replace(tzinfo=None)
    db_session.add(user)
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.query(models.User).filter_by(id=user.id).one()
    anticheat.check_action_speed(db_session, loaded, "bm0066_timezone")

    db_session.expire_all()
    loaded = db_session.query(models.User).filter_by(id=user.id).one()
    assert loaded.is_frozen is False
    assert loaded.last_action_at is not None


def test_movement_legitimacy_accepts_naive_arrival_timestamp(
    db_session,
    city,
    second_city,
):
    distance = movement.calculate_distance(city, second_city)
    speed = 1.0
    arrival = (
        utc_now() + timedelta(hours=distance / speed, minutes=1)
    ).replace(tzinfo=None)

    anticheat.check_movement_legitimacy(
        db_session,
        city,
        second_city,
        "transport",
        arrival,
        speed,
    )

    audit = (
        db_session.query(models.Log)
        .filter(
            models.Log.user_id == city.owner_id,
            models.Log.action == f"movement:transport:{city.id}->{second_city.id}",
        )
        .one()
    )
    assert "+00:00" in audit.details

import threading

import pytest
from sqlalchemy.orm import selectinload

from app import models
from app.database import SessionLocal, engine
from app.services import building as building_service
from app.services import premium as premium_service


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Concurrency guarantees require PostgreSQL row locks",
)


def _run_concurrently(callback):
    barrier = threading.Barrier(2)
    results = []

    def runner():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            callback(session)
            results.append("ok")
        except Exception as exc:  # the losing transaction is expected to fail
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    threads = [threading.Thread(target=runner) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent transaction did not finish"

    return results


def test_two_build_requests_cannot_double_spend_or_overfill_queue(db_session, city):
    status = models.PremiumStatus(user_id=city.owner_id, rubies_balance=0)
    db_session.add(status)
    db_session.commit()
    city_id = city.id

    def queue_same_upgrade(session):
        loaded_city = (
            session.query(models.City)
            .options(selectinload(models.City.owner))
            .filter(models.City.id == city_id)
            .one()
        )
        building_service.queue_upgrade(session, loaded_city, "town_hall")

    results = _run_concurrently(queue_same_upgrade)

    db_session.expire_all()
    refreshed_city = db_session.query(models.City).filter(models.City.id == city_id).one()
    queued = (
        db_session.query(models.BuildingQueue)
        .filter(models.BuildingQueue.city_id == city_id)
        .count()
    )

    assert results.count("ok") == 1
    assert queued == 1
    assert refreshed_city.wood >= 0
    assert refreshed_city.stone >= 0
    assert refreshed_city.iron >= 0
    assert refreshed_city.gold >= 0


def test_two_premium_purchases_cannot_spend_same_rubies(db_session, user):
    status = models.PremiumStatus(user_id=user.id, rubies_balance=400)
    db_session.add(status)
    db_session.commit()
    user_id = user.id

    features = iter(["second_build_queue", "second_troop_queue"])
    feature_lock = threading.Lock()

    def buy_one(session):
        with feature_lock:
            feature = next(features)
        loaded_user = session.query(models.User).filter(models.User.id == user_id).one()
        premium_service.buy_feature(session, loaded_user, feature)

    results = _run_concurrently(buy_one)

    db_session.expire_all()
    final_status = (
        db_session.query(models.PremiumStatus)
        .filter(models.PremiumStatus.user_id == user_id)
        .one()
    )

    unlocked = int(final_status.second_build_queue) + int(final_status.second_troop_queue)
    assert results.count("ok") == 1
    assert unlocked == 1
    assert final_status.rubies_balance == 50
    assert final_status.rubies_balance >= 0


def test_first_premium_status_creation_is_serialized(db_session, user):
    """Two first-time requests must create one row and preserve both grants."""

    user_id = user.id
    grants = iter([10, 20])
    grant_lock = threading.Lock()

    def grant_once(session):
        with grant_lock:
            amount = next(grants)
        loaded_user = session.query(models.User).filter(models.User.id == user_id).one()
        premium_service.grant_rubies(session, loaded_user, amount)

    results = _run_concurrently(grant_once)

    db_session.expire_all()
    rows = (
        db_session.query(models.PremiumStatus)
        .filter(models.PremiumStatus.user_id == user_id)
        .all()
    )

    assert results.count("ok") == 2
    assert len(rows) == 1
    assert rows[0].rubies_balance == 30

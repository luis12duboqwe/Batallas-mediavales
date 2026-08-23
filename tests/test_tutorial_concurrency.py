import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.database import SessionLocal, engine
from app.services import tutorial


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Tutorial reward single-claim guarantee requires PostgreSQL row locks",
)


def test_concurrent_tutorial_completion_grants_reward_once(db_session, city, user):
    user.world_id = city.world_id
    user.tutorial_step = 0
    user.tutorial_reward_claimed = False
    city.wood = city.stone = city.iron = city.gold = 1000.0

    barbarian = models.City(
        name="Tutorial Concurrent Barbarian",
        owner_id=None,
        world_id=city.world_id,
        x=11,
        y=11,
    )
    db_session.add_all(
        [
            models.Building(city_id=city.id, name="barracks", level=1),
            models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=1),
            barbarian,
        ]
    )
    db_session.flush()
    attack = models.Movement(
        origin_city_id=city.id,
        target_city_id=barbarian.id,
        world_id=city.world_id,
        movement_type="attack",
        troops={"basic_infantry": 1},
        resources={},
        spy_count=0,
        arrival_time=datetime.now(timezone.utc) - timedelta(minutes=2),
        status="completed",
    )
    db_session.add_all(
        [
            attack,
            models.Report(
                city_id=city.id,
                world_id=city.world_id,
                report_type="battle",
                content="{}",
                attacker_city_id=city.id,
                defender_city_id=barbarian.id,
            ),
            models.Report(
                city_id=city.id,
                world_id=city.world_id,
                report_type="return",
                content="{}",
                attacker_city_id=barbarian.id,
                defender_city_id=city.id,
            ),
        ]
    )
    db_session.commit()
    user_id = user.id
    city_id = city.id

    barrier = threading.Barrier(2)
    results = []
    errors = []
    lock = threading.Lock()

    def runner():
        session = SessionLocal()
        try:
            local_user = session.query(models.User).filter_by(id=user_id).one()
            barrier.wait(timeout=5)
            result = tutorial.sync_progress(session, local_user)
            with lock:
                results.append(result)
        except Exception as exc:
            session.rollback()
            with lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=runner) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent tutorial completion did not finish"

    assert errors == []
    assert len(results) == 2
    assert all(result["step"] == tutorial.FINAL_STEP for result in results)
    assert sum(bool(result["reward_granted_now"]) for result in results) == 1

    db_session.expire_all()
    final_user = db_session.query(models.User).filter_by(id=user_id).one()
    final_city = db_session.query(models.City).filter_by(id=city_id).one()
    assert final_user.tutorial_reward_claimed is True
    assert final_user.tutorial_step == tutorial.FINAL_STEP
    assert final_city.wood == pytest.approx(1250.0)
    assert final_city.stone == pytest.approx(1250.0)
    assert final_city.iron == pytest.approx(1250.0)
    assert final_city.gold == pytest.approx(1250.0)

import threading

import pytest

from app import models
from app.database import SessionLocal, engine
from app.services import achievement

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="BM-0071 honor medal concurrency guarantees require PostgreSQL row locks",
)


def test_concurrent_honor_progress_keeps_both_increments(db_session, user, city):
    medal = models.Achievement(
        title="Concurrent Honor",
        description="Concurrency recognition",
        category="honor",
        requirement_type="concurrent_honor",
        requirement_value=2,
        reward_type="resources",
        reward_value="999999",
    )
    membership = (
        db_session.query(models.PlayerWorld)
        .filter_by(user_id=user.id, world_id=city.world_id)
        .one_or_none()
    )
    if membership is None:
        db_session.add(models.PlayerWorld(user_id=user.id, world_id=city.world_id))
    db_session.add(medal)
    db_session.commit()

    barrier = threading.Barrier(2)
    errors = []
    lock = threading.Lock()

    def worker():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            achievement.update_achievement_progress(
                session,
                user.id,
                city.world_id,
                "concurrent_honor",
                increment=1,
            )
        except Exception as exc:  # pragma: no cover - asserted below on PostgreSQL
            session.rollback()
            with lock:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "Concurrent BM-0071 medal update did not finish"

    assert errors == []
    db_session.expire_all()
    progress = (
        db_session.query(models.AchievementProgress)
        .filter_by(
            user_id=user.id,
            achievement_id=medal.id,
            world_id=city.world_id,
        )
        .one()
    )
    assert progress.current_progress == 2
    assert progress.status == "completed"
    assert (
        db_session.query(models.AchievementProgress)
        .filter_by(
            user_id=user.id,
            achievement_id=medal.id,
            world_id=city.world_id,
        )
        .count()
        == 1
    )

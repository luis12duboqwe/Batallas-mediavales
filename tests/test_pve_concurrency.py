import threading
from datetime import datetime, timezone

import pytest

from app import models
from app.database import SessionLocal, engine
from app.seed import DEFAULT_WORLD_NAME, seed_game
from app.services import pve


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="PvE tick single-consumer guarantee requires PostgreSQL row locks",
)


def test_two_workers_process_same_pve_bucket_once(db_session):
    seed_game(db_session)
    world = (
        db_session.query(models.World)
        .filter(models.World.name == DEFAULT_WORLD_NAME)
        .one()
    )
    oasis = (
        db_session.query(models.Oasis)
        .filter(models.Oasis.world_id == world.id, models.Oasis.owner_city_id.is_(None))
        .order_by(models.Oasis.id.asc())
        .first()
    )
    assert oasis is not None
    oasis.troops = {}
    oasis_id = oasis.id
    db_session.commit()

    barrier = threading.Barrier(2)
    results: list[dict | Exception | None] = [None, None]
    tick_at = datetime(2026, 8, 25, 16, 0, tzinfo=timezone.utc)

    def runner(index: int) -> None:
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            results[index] = pve.process_pve_tick(session, now=tick_at)
            session.commit()
        except Exception as exc:  # pragma: no cover - diagnostic path
            session.rollback()
            results[index] = exc
        finally:
            session.close()

    threads = [threading.Thread(target=runner, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive(), "Concurrent PvE tick did not finish"

    assert not any(isinstance(result, Exception) for result in results), results
    processed_counts = sorted(int(result["worlds_processed"]) for result in results if isinstance(result, dict))
    assert processed_counts == [0, 1]

    db_session.expire_all()
    oasis = db_session.query(models.Oasis).filter(models.Oasis.id == oasis_id).one()
    profile = pve.OASIS_PROFILES[pve.oasis_tier(oasis)]
    for unit, amount in oasis.troops.items():
        assert 0 < amount <= profile["guards"][unit]

"""Two independent PostgreSQL sessions must never overfund or double-charge."""
import threading
from uuid import uuid4

import pytest

from app import models
from app.database import SessionLocal, engine
from app.services import wonder_funding

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Requires PostgreSQL row locks")


def _fixture(db_session, user, city):
    city.world.wonder_rules_version = "alliance-v2"
    alliance = models.Alliance(name="PGWonder", leader_id=user.id, world_id=city.world_id)
    db_session.add(alliance)
    db_session.flush()
    db_session.add(models.AllianceMember(alliance_id=alliance.id, user_id=user.id, rank=3))
    db_session.add_all([
        models.Building(city_id=city.id, name="town_hall", level=20),
        models.Building(city_id=city.id, name="warehouse", level=20),
        models.Building(city_id=city.id, name="cathedral", level=10),
    ])
    city.wood = 6000
    db_session.commit()


@pytest.mark.parametrize("same_key", [False, True])
def test_parallel_funding_is_serialized_and_exactly_once(db_session, user, city, same_key):
    _fixture(db_session, user, city)
    # Share only immutable scalar identifiers between worker threads, never
    # live ORM objects bound to the setup session.
    world_id, city_id, contributor_id = city.world_id, city.id, user.id
    barrier = threading.Barrier(2)
    key = uuid4().hex
    observations = []
    errors = []
    guard = threading.Lock()

    def worker(n):
        session = SessionLocal()
        try:
            barrier.wait(timeout=10)
            snapshot = wonder_funding.contribute(
                session, world_id=world_id, contributor_id=contributor_id,
                target_city_id=city_id, source_city_id=city_id,
                amounts={"wood": 5000},
                idempotency_key=key if same_key else f"{key}{n}",
            )
            with guard:
                observations.append(snapshot)
        except Exception as exc:
            with guard:
                errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive(), "Wonder financing deadlocked under concurrent requests"

    if same_key:
        assert len(errors) == 0
        assert len(observations) == 2
    else:
        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)
        assert "Insufficient" in str(errors[0])
        assert len(observations) == 1

    db_session.expire_all()
    assert db_session.get(models.City, city_id).wood < 1100
    assert db_session.query(models.WonderContribution).count() == 1
    funding = db_session.query(models.WonderFunding).one()
    assert funding.funded_wood == 5000

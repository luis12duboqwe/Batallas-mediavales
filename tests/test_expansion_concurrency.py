import threading

import pytest

from app import models
from app.database import SessionLocal, engine
from app.services import balance, expansion, world_gen
from app.utils import utc_now


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Expansion concurrency guarantees require PostgreSQL row locks",
)


def _run_parallel(callbacks):
    barrier = threading.Barrier(len(callbacks))
    results = [None] * len(callbacks)

    def runner(index, callback):
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            callback(session)
            results[index] = "ok"
        except Exception as exc:
            session.rollback()
            results[index] = type(exc).__name__
        finally:
            session.close()

    threads = [
        threading.Thread(target=runner, args=(index, callback))
        for index, callback in enumerate(callbacks)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive(), "Concurrent expansion transaction did not finish"

    return results


def _valid_coords(start: int, count: int):
    coords = []
    value = start
    while len(coords) < count:
        candidate = (value, value + 1)
        if world_gen.get_tile_type(*candidate) != "water":
            coords.append(candidate)
        value += 2
    return coords


def test_two_foundings_cannot_double_spend_same_expansion_points(db_session, user, city):
    membership = models.PlayerWorld(
        user_id=user.id,
        world_id=city.world_id,
        starting_city_id=city.id,
        expansion_points=balance.SETTLEMENT_EXPANSION_POINT_COSTS["camp"],
    )
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, 1000.0)
    city.last_production = utc_now()
    db_session.add(membership)
    db_session.add(city)
    db_session.commit()

    user_id = user.id
    origin_id = city.id
    world_id = city.world_id
    coords = _valid_coords(60, 2)

    def found_at(x, y, name):
        def callback(session):
            owner = session.query(models.User).filter_by(id=user_id).one()
            origin = session.query(models.City).filter_by(id=origin_id).one()
            expansion.found_settlement(
                session,
                owner,
                origin,
                name,
                x,
                y,
                "camp",
            )

        return callback

    results = _run_parallel(
        [
            found_at(*coords[0], "Concurrent Camp A"),
            found_at(*coords[1], "Concurrent Camp B"),
        ]
    )

    db_session.expire_all()
    membership_after = (
        db_session.query(models.PlayerWorld)
        .filter_by(user_id=user_id, world_id=world_id)
        .one()
    )
    origin_after = db_session.query(models.City).filter_by(id=origin_id).one()
    camps = (
        db_session.query(models.City)
        .filter_by(owner_id=user_id, world_id=world_id, settlement_type="camp")
        .all()
    )

    assert results.count("ok") == 1
    assert len(camps) == 1
    assert membership_after.expansion_points == 0
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(origin_after, resource) == pytest.approx(
            1000.0 - balance.CAMP_FOUNDING_COST.get(resource, 0.0),
            abs=0.1,
        )
        assert getattr(origin_after, resource) >= 0


def test_parallel_point_awards_are_not_lost(db_session, user, city):
    membership = models.PlayerWorld(
        user_id=user.id,
        world_id=city.world_id,
        starting_city_id=city.id,
        expansion_points=0,
    )
    second_city = models.City(
        name="Expansion Generator Two",
        owner_id=user.id,
        world_id=city.world_id,
        x=70,
        y=71,
        settlement_type="city",
    )
    db_session.add_all([membership, second_city])
    db_session.commit()

    city_ids = [city.id, second_city.id]
    user_id = user.id
    world_id = city.world_id

    def award(city_id):
        def callback(session):
            loaded = session.query(models.City).filter_by(id=city_id).one()
            awarded = expansion.award_expansion_points_for_building(
                session,
                loaded,
                "church",
            )
            assert awarded == balance.EXPANSION_POINTS_PER_COMPLETION["church"]
            session.commit()

        return callback

    results = _run_parallel([award(city_ids[0]), award(city_ids[1])])

    db_session.expire_all()
    membership_after = (
        db_session.query(models.PlayerWorld)
        .filter_by(user_id=user_id, world_id=world_id)
        .one()
    )

    assert results == ["ok", "ok"]
    assert membership_after.expansion_points == 2

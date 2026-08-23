import threading

import pytest

from app import models, schemas
from app.database import SessionLocal, engine
from app.services import market
from app.utils import utc_now


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Market concurrency guarantees require PostgreSQL row locks",
)


def _market_city(db_session, world_id: int, *, username: str, x: int, y: int):
    user = models.User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    city = models.City(
        name=f"Market {username}",
        owner_id=user.id,
        world_id=world_id,
        x=x,
        y=y,
        wood=1000,
        stone=1000,
        iron=1000,
        gold=1000,
        last_production=utc_now(),
    )
    db_session.add(city)
    db_session.flush()
    db_session.add(models.Building(city_id=city.id, name="market", level=2))
    db_session.commit()
    db_session.refresh(city)
    return city


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
        assert not thread.is_alive(), "Concurrent market transaction did not finish"

    return results


def _create_offer(db_session, seller):
    return market.create_offer(
        db_session,
        seller,
        schemas.MarketOfferCreate(
            offer_type="wood",
            offer_amount=100,
            request_type="gold",
            request_amount=50,
            is_alliance_only=False,
        ),
    )


def test_two_buyers_cannot_accept_the_same_offer_twice(db_session, city):
    world_id = city.world_id
    city.wood = city.stone = city.iron = city.gold = 1000
    city.last_production = utc_now()
    db_session.add(models.Building(city_id=city.id, name="market", level=2))
    db_session.commit()

    buyer_a = _market_city(db_session, world_id, username="buyer_a", x=40, y=40)
    buyer_b = _market_city(db_session, world_id, username="buyer_b", x=41, y=41)
    offer = _create_offer(db_session, city)
    offer_id = offer.id
    buyer_ids = [buyer_a.id, buyer_b.id]

    def accept_with(buyer_id):
        def callback(session):
            buyer = session.query(models.City).filter(models.City.id == buyer_id).one()
            market.accept_offer(session, buyer, offer_id)

        return callback

    results = _run_parallel([accept_with(buyer_a.id), accept_with(buyer_b.id)])

    db_session.expire_all()
    seller = db_session.query(models.City).filter(models.City.id == city.id).one()
    buyers = {
        buyer.id: buyer
        for buyer in db_session.query(models.City)
        .filter(models.City.id.in_(buyer_ids))
        .all()
    }
    transports = (
        db_session.query(models.Movement)
        .filter(models.Movement.movement_type == "transport")
        .all()
    )

    assert results.count("ok") == 1
    assert db_session.query(models.MarketOffer).filter_by(id=offer_id).one_or_none() is None
    assert len(transports) == 2
    assert seller.wood == pytest.approx(900, abs=0.1)
    assert sorted([buyers[buyer_a.id].gold, buyers[buyer_b.id].gold]) == pytest.approx(
        [950, 1000], abs=0.1
    )
    assert all(value >= 0 for value in [seller.wood, seller.stone, seller.iron, seller.gold])
    for buyer in buyers.values():
        assert buyer.wood >= 0 and buyer.stone >= 0 and buyer.iron >= 0 and buyer.gold >= 0


def test_accept_vs_cancel_same_offer_has_one_atomic_winner(db_session, city):
    world_id = city.world_id
    city.wood = city.stone = city.iron = city.gold = 1000
    city.last_production = utc_now()
    db_session.add(models.Building(city_id=city.id, name="market", level=2))
    db_session.commit()

    buyer = _market_city(db_session, world_id, username="buyer_cancel_race", x=42, y=42)
    offer = _create_offer(db_session, city)
    offer_id = offer.id
    seller_id = city.id
    buyer_id = buyer.id

    def accept(session):
        loaded_buyer = session.query(models.City).filter(models.City.id == buyer_id).one()
        market.accept_offer(session, loaded_buyer, offer_id)

    def cancel(session):
        seller = session.query(models.City).filter(models.City.id == seller_id).one()
        market.cancel_offer(session, seller, offer_id)

    results = _run_parallel([accept, cancel])

    db_session.expire_all()
    seller = db_session.query(models.City).filter(models.City.id == seller_id).one()
    buyer_after = db_session.query(models.City).filter(models.City.id == buyer_id).one()
    offer_after = db_session.query(models.MarketOffer).filter_by(id=offer_id).one_or_none()
    transports = (
        db_session.query(models.Movement)
        .filter(models.Movement.movement_type == "transport")
        .all()
    )

    assert results.count("ok") == 1
    assert offer_after is None
    assert seller.wood >= 0 and buyer_after.gold >= 0

    if len(transports) == 2:
        # Acceptance won: seller's wood stays reserved and buyer paid gold once.
        assert seller.wood == pytest.approx(900, abs=0.1)
        assert buyer_after.gold == pytest.approx(950, abs=0.1)
    else:
        # Cancellation won: reservation was refunded and buyer was untouched.
        assert transports == []
        assert seller.wood == pytest.approx(1000, abs=0.1)
        assert buyer_after.gold == pytest.approx(1000, abs=0.1)

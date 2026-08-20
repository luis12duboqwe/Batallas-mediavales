import pytest

from app import models, schemas
from app.services import market
from app.utils import utc_now


def _add_market(db_session, city: models.City, level: int = 2) -> None:
    db_session.add(models.Building(city_id=city.id, name="market", level=level))
    db_session.commit()


def _create_other_player_city(db_session, world_id: int, *, x: int, y: int):
    user = models.User(
        username=f"merchant_{x}_{y}",
        email=f"merchant_{x}_{y}@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    city = models.City(
        name=f"Merchant {x},{y}",
        owner_id=user.id,
        world_id=world_id,
        x=x,
        y=y,
        wood=1000,
        clay=1000,
        iron=1000,
        last_production=utc_now(),
    )
    db_session.add(city)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(city)
    return user, city


def _reset_resources(db_session, city: models.City, *, wood=1000, clay=1000, iron=1000):
    city.wood = wood
    city.clay = clay
    city.iron = iron
    city.last_production = utc_now()
    db_session.add(city)
    db_session.commit()
    db_session.refresh(city)


def test_direct_transport_charges_resources_exactly_once(db_session, city):
    _reset_resources(db_session, city)
    _add_market(db_session, city)
    _, target = _create_other_player_city(db_session, city.world_id, x=8, y=9)

    movement = market.send_resources(
        db_session,
        city,
        schemas.TransportRequest(target_city_id=target.id, wood=100, clay=0, iron=0),
    )

    db_session.refresh(city)
    assert city.wood == pytest.approx(900, abs=0.1)
    assert movement.resources == {"wood": 100}
    assert movement.origin_city_id == city.id
    assert movement.target_city_id == target.id
    assert db_session.query(models.Movement).filter_by(id=movement.id).count() == 1


def test_offer_acceptance_charges_each_side_once_and_creates_both_transports(db_session, city):
    _reset_resources(db_session, city)
    _add_market(db_session, city)
    _, buyer = _create_other_player_city(db_session, city.world_id, x=12, y=13)
    _add_market(db_session, buyer)

    offer = market.create_offer(
        db_session,
        city,
        schemas.MarketOfferCreate(
            offer_type="wood",
            offer_amount=100,
            request_type="clay",
            request_amount=50,
            is_alliance_only=False,
        ),
    )
    db_session.refresh(city)
    assert city.wood == pytest.approx(900, abs=0.1)

    seller_movement, buyer_movement = market.accept_offer(db_session, buyer, offer.id)

    db_session.refresh(city)
    db_session.refresh(buyer)
    assert city.wood == pytest.approx(900, abs=0.1)
    assert buyer.clay == pytest.approx(950, abs=0.1)
    assert db_session.query(models.MarketOffer).filter_by(id=offer.id).one_or_none() is None

    assert seller_movement.origin_city_id == city.id
    assert seller_movement.target_city_id == buyer.id
    assert seller_movement.resources == {"wood": 100}
    assert buyer_movement.origin_city_id == buyer.id
    assert buyer_movement.target_city_id == city.id
    assert buyer_movement.resources == {"clay": 50}


def test_offer_acceptance_rolls_back_everything_if_second_transport_fails(
    db_session,
    city,
    monkeypatch,
):
    _reset_resources(db_session, city)
    _add_market(db_session, city)
    _, buyer = _create_other_player_city(db_session, city.world_id, x=16, y=17)
    _add_market(db_session, buyer)

    offer = market.create_offer(
        db_session,
        city,
        schemas.MarketOfferCreate(
            offer_type="wood",
            offer_amount=100,
            request_type="clay",
            request_amount=50,
            is_alliance_only=False,
        ),
    )
    db_session.refresh(city)
    seller_reserved_balance = city.wood
    buyer_balance = buyer.clay

    original_create = market._create_transport_uncommitted
    calls = 0

    def fail_second_transport(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated second transport failure")
        return original_create(*args, **kwargs)

    monkeypatch.setattr(market, "_create_transport_uncommitted", fail_second_transport)

    with pytest.raises(RuntimeError, match="simulated second transport failure"):
        market.accept_offer(db_session, buyer, offer.id)

    db_session.expire_all()
    seller_after = db_session.query(models.City).filter_by(id=city.id).one()
    buyer_after = db_session.query(models.City).filter_by(id=buyer.id).one()
    persisted_offer = db_session.query(models.MarketOffer).filter_by(id=offer.id).one_or_none()
    transports = db_session.query(models.Movement).filter(
        models.Movement.movement_type == "transport"
    ).all()

    assert seller_after.wood == pytest.approx(seller_reserved_balance, abs=0.1)
    assert buyer_after.clay == pytest.approx(buyer_balance, abs=0.1)
    assert persisted_offer is not None
    assert transports == []

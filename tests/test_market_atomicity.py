from datetime import timedelta

import pytest
from fastapi import HTTPException

from app import models, schemas
from app.services import balance, market
from app.services import movement as movement_service
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
        stone=1000,
        iron=1000,
        gold=1000,
        last_production=utc_now(),
    )
    db_session.add(city)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(city)
    return user, city


def _reset_resources(
    db_session,
    city: models.City,
    *,
    wood=1000,
    stone=1000,
    iron=1000,
    gold=1000,
):
    city.wood = wood
    city.stone = stone
    city.iron = iron
    city.gold = gold
    city.last_production = utc_now()
    db_session.add(city)
    db_session.commit()
    db_session.refresh(city)


def _make_due(db_session, movement: models.Movement) -> None:
    movement.arrival_time = utc_now() - timedelta(seconds=1)
    db_session.add(movement)
    db_session.commit()


def test_commerce_is_available_from_start_and_market_only_expands_capacity(db_session, city):
    _reset_resources(db_session, city)
    _, target = _create_other_player_city(db_session, city.world_id, x=6, y=7)

    assert all(building.name != "market" for building in city.buildings)
    assert market._get_market_capacity(city) == balance.BASE_MERCHANT_CAPACITY == 500

    transport = market.send_resources(
        db_session,
        city,
        schemas.TransportRequest(
            target_city_id=target.id,
            wood=500,
            stone=0,
            iron=0,
            gold=0,
        ),
    )
    assert transport.resources == {"wood": 500}
    assert market._get_available_merchants(db_session, city) == 0

    _add_market(db_session, city, level=1)
    db_session.expire(city, ["buildings"])
    assert market._get_market_capacity(city) == 1500
    assert market._get_available_merchants(db_session, city) == 1000


def test_generic_movement_api_cannot_bypass_market_transport_rules(db_session, city):
    _reset_resources(db_session, city)
    _, target = _create_other_player_city(db_session, city.world_id, x=7, y=8)

    with pytest.raises(ValueError, match="market service"):
        movement_service.send_movement(
            db_session,
            city,
            target.id,
            "transport",
            resources={"wood": 10},
        )

    db_session.refresh(city)
    assert city.wood == pytest.approx(1000, abs=0.1)
    assert (
        db_session.query(models.Movement)
        .filter(models.Movement.movement_type == "transport")
        .count()
        == 0
    )


def test_offer_contract_limits_ratio_count_and_alliance_acceptance(db_session, city):
    _reset_resources(db_session, city)
    buyer_user, buyer = _create_other_player_city(db_session, city.world_id, x=9, y=10)

    with pytest.raises(HTTPException, match="resources must be different"):
        market.create_offer(
            db_session,
            city,
            schemas.MarketOfferCreate(
                offer_type="wood",
                offer_amount=100,
                request_type="wood",
                request_amount=100,
                is_alliance_only=False,
            ),
        )

    with pytest.raises(HTTPException, match="ratio"):
        market.create_offer(
            db_session,
            city,
            schemas.MarketOfferCreate(
                offer_type="wood",
                offer_amount=100,
                request_type="stone",
                request_amount=500,
                is_alliance_only=False,
            ),
        )

    seller_user = db_session.query(models.User).filter(models.User.id == city.owner_id).one()
    alliance = models.Alliance(
        name="BM0066 Traders",
        description="",
        diplomacy="neutral",
        leader_id=seller_user.id,
        world_id=city.world_id,
    )
    db_session.add(alliance)
    db_session.flush()
    db_session.add(
        models.AllianceMember(alliance_id=alliance.id, user_id=seller_user.id, rank=2)
    )
    db_session.commit()

    restricted_offer = market.create_offer(
        db_session,
        city,
        schemas.MarketOfferCreate(
            offer_type="wood",
            offer_amount=100,
            request_type="stone",
            request_amount=100,
            is_alliance_only=True,
        ),
    )
    with pytest.raises(HTTPException) as denied:
        market.accept_offer(db_session, buyer, restricted_offer.id)
    assert denied.value.status_code == 403

    db_session.add(
        models.AllianceMember(alliance_id=alliance.id, user_id=buyer_user.id, rank=0)
    )
    db_session.commit()
    seller_movement, buyer_movement = market.accept_offer(
        db_session, buyer, restricted_offer.id
    )
    assert seller_movement.resources == {"wood": 100}
    assert buyer_movement.resources == {"stone": 100}

    # Five small offers are allowed; the sixth is rejected independently of
    # the remaining merchant capacity.
    for _ in range(balance.MAX_ACTIVE_MARKET_OFFERS):
        market.create_offer(
            db_session,
            city,
            schemas.MarketOfferCreate(
                offer_type="iron",
                offer_amount=10,
                request_type="gold",
                request_amount=10,
                is_alliance_only=False,
            ),
        )
    with pytest.raises(HTTPException, match="Maximum active market offers"):
        market.create_offer(
            db_session,
            city,
            schemas.MarketOfferCreate(
                offer_type="iron",
                offer_amount=10,
                request_type="gold",
                request_amount=10,
                is_alliance_only=False,
            ),
        )


def test_npc_trade_is_bounded_and_applies_resource_sink(db_session, city):
    _reset_resources(db_session, city)

    result = market.npc_trade(db_session, city, "wood", "stone", 100)
    db_session.refresh(city)

    assert result["rules_version"] == balance.COMMERCE_RULES_VERSION
    assert result["rate"] == pytest.approx(0.80)
    assert result["received_amount"] == 80
    assert city.wood == pytest.approx(900, abs=0.1)
    assert city.stone == pytest.approx(1080, abs=0.1)

    with pytest.raises(HTTPException, match="NPC trade amount"):
        market.npc_trade(
            db_session,
            city,
            "wood",
            "stone",
            balance.NPC_TRADE_MAX_AMOUNT + 1,
        )


def test_direct_transport_charges_resources_exactly_once(db_session, city):
    _reset_resources(db_session, city)
    _add_market(db_session, city)
    _, target = _create_other_player_city(db_session, city.world_id, x=8, y=9)

    movement = market.send_resources(
        db_session,
        city,
        schemas.TransportRequest(
            target_city_id=target.id,
            wood=100,
            stone=0,
            iron=0,
            gold=0,
        ),
    )

    db_session.refresh(city)
    assert city.wood == pytest.approx(900, abs=0.1)
    assert city.gold == pytest.approx(1000, abs=0.1)
    assert movement.resources == {"wood": 100}
    assert movement.origin_city_id == city.id
    assert movement.target_city_id == target.id
    assert db_session.query(models.Movement).filter_by(id=movement.id).count() == 1


def test_merchant_capacity_stays_reserved_until_transport_return(db_session, city):
    _reset_resources(db_session, city)
    _, target = _create_other_player_city(db_session, city.world_id, x=11, y=12)

    transport = market.send_resources(
        db_session,
        city,
        schemas.TransportRequest(target_city_id=target.id, wood=100),
    )
    assert market._get_available_merchants(db_session, city) == 400

    _make_due(db_session, transport)
    movement_service.resolve_due_movements(db_session)
    db_session.expire_all()

    target_after = db_session.query(models.City).filter_by(id=target.id).one()
    assert target_after.wood == pytest.approx(1100, abs=0.1)
    merchant_return = (
        db_session.query(models.Movement)
        .filter_by(
            target_city_id=city.id,
            movement_type="transport_return",
            status="ongoing",
        )
        .one()
    )
    assert merchant_return.resources == {"capacity": 100}
    sender_after = db_session.query(models.City).filter_by(id=city.id).one()
    assert market._get_available_merchants(db_session, sender_after) == 400

    _make_due(db_session, merchant_return)
    movement_service.resolve_due_movements(db_session)
    db_session.expire_all()
    sender_after = db_session.query(models.City).filter_by(id=city.id).one()
    assert market._get_available_merchants(db_session, sender_after) == 500


def test_full_destination_returns_complete_cargo_without_loss(db_session, city):
    _reset_resources(db_session, city)
    _, target = _create_other_player_city(db_session, city.world_id, x=13, y=14)
    _reset_resources(db_session, target, wood=4950)

    transport = market.send_resources(
        db_session,
        city,
        schemas.TransportRequest(target_city_id=target.id, wood=100),
    )
    _make_due(db_session, transport)
    movement_service.resolve_due_movements(db_session)
    db_session.expire_all()

    target_after = db_session.query(models.City).filter_by(id=target.id).one()
    sender_after = db_session.query(models.City).filter_by(id=city.id).one()
    assert target_after.wood == pytest.approx(4950, abs=0.1)
    merchant_return = (
        db_session.query(models.Movement)
        .filter_by(
            target_city_id=city.id,
            movement_type="transport_return",
            status="ongoing",
        )
        .one()
    )
    assert merchant_return.resources == {"capacity": 100, "wood": 100}
    assert market._get_available_merchants(db_session, sender_after) == 400

    # If the sender refilled its warehouse while the merchants travelled, the
    # cargo remains on the ongoing return instead of being clipped or lost.
    sender_after.wood = 5000
    sender_after.last_production = utc_now()
    db_session.add(sender_after)
    db_session.commit()
    _make_due(db_session, merchant_return)
    movement_service.resolve_due_movements(db_session)
    db_session.expire_all()

    pending_return = db_session.query(models.Movement).filter_by(id=merchant_return.id).one()
    sender_full = db_session.query(models.City).filter_by(id=city.id).one()
    assert pending_return.status == "ongoing"
    assert pending_return.resources == {"capacity": 100, "wood": 100}
    assert sender_full.wood == pytest.approx(5000, abs=0.1)
    assert market._get_available_merchants(db_session, sender_full) == 400

    sender_full.wood = 4800
    sender_full.last_production = utc_now()
    db_session.add(sender_full)
    db_session.commit()
    movement_service.resolve_due_movements(db_session)
    db_session.expire_all()

    completed_return = db_session.query(models.Movement).filter_by(id=merchant_return.id).one()
    sender_final = db_session.query(models.City).filter_by(id=city.id).one()
    assert completed_return.status == "completed"
    assert sender_final.wood == pytest.approx(4900, abs=0.1)
    assert market._get_available_merchants(db_session, sender_final) == 500


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
            request_type="stone",
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
    assert buyer.stone == pytest.approx(950, abs=0.1)
    assert buyer.gold == pytest.approx(1000, abs=0.1)
    assert db_session.query(models.MarketOffer).filter_by(id=offer.id).one_or_none() is None

    assert seller_movement.origin_city_id == city.id
    assert seller_movement.target_city_id == buyer.id
    assert seller_movement.resources == {"wood": 100}
    assert buyer_movement.origin_city_id == buyer.id
    assert buyer_movement.target_city_id == city.id
    assert buyer_movement.resources == {"stone": 50}


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
            request_type="stone",
            request_amount=50,
            is_alliance_only=False,
        ),
    )
    db_session.refresh(city)
    seller_reserved_balance = city.wood
    buyer_balance = buyer.stone

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
    assert buyer_after.stone == pytest.approx(buyer_balance, abs=0.1)
    assert persisted_offer is not None
    assert transports == []

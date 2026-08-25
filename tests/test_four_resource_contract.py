import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import models, schemas
from app.services import balance, market
from app.utils import utc_now


def _add_market(db_session, city: models.City, level: int = 2) -> None:
    db_session.add(models.Building(city_id=city.id, name="market", level=level))
    db_session.commit()


def _target_city(db_session, world_id: int) -> models.City:
    """Create a valid player-owned transport target for spend validation."""

    owner = models.User(
        username="four_resource_target",
        email="four-resource-target@example.com",
        hashed_password="placeholder",
        is_verified=True,
    )
    db_session.add(owner)
    db_session.flush()
    target = models.City(
        name="Four Resource Target",
        owner_id=owner.id,
        world_id=world_id,
        x=70,
        y=71,
        wood=500,
        stone=500,
        iron=500,
        gold=500,
        last_production=utc_now(),
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)
    return target


def test_canonical_resource_contract_has_no_runtime_clay():
    assert balance.RESOURCE_FIELDS == ("wood", "stone", "iron", "gold")
    assert "clay" not in balance.RESOURCE_FIELDS


def test_market_offer_rejects_legacy_clay_resource_type():
    with pytest.raises(ValidationError):
        schemas.MarketOfferCreate(
            offer_type="clay",
            offer_amount=10,
            request_type="gold",
            request_amount=10,
        )


def test_transport_rejects_legacy_clay_field_instead_of_ignoring_it():
    with pytest.raises(ValidationError):
        schemas.TransportRequest(
            target_city_id=2,
            wood=0,
            stone=0,
            iron=0,
            gold=0,
            clay=10,
        )


def test_transport_rejects_negative_gold():
    with pytest.raises(ValidationError):
        schemas.TransportRequest(target_city_id=2, gold=-1)


@pytest.mark.parametrize("resource", ["stone", "gold"])
def test_transport_cannot_spend_more_stone_or_gold_than_city_owns(
    db_session,
    city,
    resource,
):
    _add_market(db_session, city)
    target = _target_city(db_session, city.world_id)

    for name in balance.RESOURCE_FIELDS:
        setattr(city, name, 1000.0)
    setattr(city, resource, 0.0)
    city.last_production = utc_now()
    db_session.add(city)
    db_session.commit()

    payload = {
        "target_city_id": target.id,
        "wood": 0,
        "stone": 0,
        "iron": 0,
        "gold": 0,
    }
    payload[resource] = 1

    with pytest.raises(HTTPException, match="Insufficient resources"):
        market.send_resources(
            db_session,
            city,
            schemas.TransportRequest(**payload),
        )

    db_session.expire_all()
    persisted = db_session.query(models.City).filter_by(id=city.id).one()
    assert getattr(persisted, resource) < 1
    assert db_session.query(models.Movement).filter_by(movement_type="transport").count() == 0

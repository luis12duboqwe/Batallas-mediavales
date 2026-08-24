from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.routers.auth import create_access_token
from app.services import balance, production, troops, upkeep


FIXED_NOW = datetime(2026, 8, 23, 22, 0, tzinfo=timezone.utc)


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _target_city(db_session, city, x=20, y=20):
    target = models.City(
        name="Upkeep Target",
        owner_id=None,
        world_id=city.world_id,
        x=x,
        y=y,
    )
    db_session.add(target)
    db_session.commit()
    db_session.refresh(target)
    return target


def test_committed_upkeep_counts_home_outgoing_spy_and_returning_armies(
    db_session, city
):
    target = _target_city(db_session, city)
    db_session.add(models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=10))
    db_session.add_all(
        [
            models.Movement(
                origin_city_id=city.id,
                target_city_id=target.id,
                world_id=city.world_id,
                movement_type="attack",
                troops={"heavy_infantry": 5},
                resources={},
                spy_count=0,
                arrival_time=FIXED_NOW + timedelta(hours=1),
                status="ongoing",
            ),
            models.Movement(
                origin_city_id=city.id,
                target_city_id=target.id,
                world_id=city.world_id,
                movement_type="spy",
                troops={},
                resources={},
                spy_count=2,
                arrival_time=FIXED_NOW + timedelta(hours=1),
                status="ongoing",
            ),
            models.Movement(
                origin_city_id=target.id,
                target_city_id=city.id,
                world_id=city.world_id,
                movement_type="return",
                troops={"fast_cavalry": 3},
                resources={},
                spy_count=0,
                arrival_time=FIXED_NOW + timedelta(hours=1),
                status="ongoing",
            ),
        ]
    )
    db_session.commit()

    expected = (
        10 * balance.UNIT_CATALOG["basic_infantry"]["upkeep_per_hour"]
        + 5 * balance.UNIT_CATALOG["heavy_infantry"]["upkeep_per_hour"]
        + 2 * balance.UNIT_CATALOG["spy"]["upkeep_per_hour"]
        + 3 * balance.UNIT_CATALOG["fast_cavalry"]["upkeep_per_hour"]
    )
    assert upkeep.get_committed_upkeep_per_hour(db_session, city) == pytest.approx(expected)


def test_training_queue_reserves_future_upkeep(db_session, city):
    db_session.add(
        models.TroopQueue(
            city_id=city.id,
            troop_type="heavy_cavalry",
            amount=4,
            finish_time=FIXED_NOW + timedelta(hours=1),
            paid_cost={},
        )
    )
    db_session.commit()

    expected = 4 * balance.UNIT_CATALOG["heavy_cavalry"]["upkeep_per_hour"]
    assert upkeep.get_reserved_upkeep_per_hour(db_session, city.id) == pytest.approx(expected)
    status = upkeep.get_upkeep_status(db_session, city)
    assert status["reserved_per_hour"] == pytest.approx(expected)
    assert status["capacity_per_hour"] == pytest.approx(
        balance.PRODUCTION_RATES_PER_HOUR["gold"]
    )
    assert status["available_per_hour"] == pytest.approx(
        balance.PRODUCTION_RATES_PER_HOUR["gold"] - expected
    )


def test_stable_upkeep_capacity_ignores_temporary_production_event(
    db_session, city, monkeypatch
):
    monkeypatch.setattr(
        production.event_service,
        "get_active_modifiers",
        lambda db, world_id: {
            **balance.EVENT_DEFAULT_MODIFIERS,
            "production_speed": 2.0,
        },
    )

    gross = production.get_gross_production_per_hour(db_session, city)
    assert gross["gold"] == pytest.approx(16.0)
    assert upkeep.get_stable_upkeep_capacity_per_hour(db_session, city) == pytest.approx(8.0)


def test_net_gold_production_deducts_committed_upkeep(db_session, city, monkeypatch):
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)
    city.gold = 100.0
    city.last_production = FIXED_NOW - timedelta(hours=1)
    db_session.add(models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=100))
    db_session.commit()

    net = production.get_production_per_hour(db_session, city)
    assert net["gold"] == pytest.approx(8.0 - 2.0)

    production.recalculate_resources(db_session, city)
    db_session.refresh(city)
    assert city.gold == pytest.approx(106.0)


def test_unsustainable_existing_army_drains_gold_to_zero_without_debt(
    db_session, city, monkeypatch
):
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)
    city.gold = 1.0
    city.last_production = FIXED_NOW - timedelta(hours=1)
    db_session.add(models.Troop(city_id=city.id, unit_type="noble", quantity=20))
    db_session.commit()

    assert production.get_production_per_hour(db_session, city)["gold"] == pytest.approx(-2.0)
    production.recalculate_resources(db_session, city)
    db_session.refresh(city)
    assert city.gold == pytest.approx(0.0)


def test_training_rejects_upkeep_overbooking_before_spending(
    db_session, city, monkeypatch
):
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(troops, "utc_now", lambda: FIXED_NOW)
    city.population_max = 1000
    city.last_production = FIXED_NOW
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, 5000.0)
    db_session.add(models.Building(city_id=city.id, name="barracks", level=1))
    db_session.commit()

    before = {resource: float(getattr(city, resource)) for resource in balance.RESOURCE_FIELDS}
    max_basic = int(
        balance.PRODUCTION_RATES_PER_HOUR["gold"]
        / balance.UNIT_CATALOG["basic_infantry"]["upkeep_per_hour"]
    )

    with pytest.raises(ValueError, match="sustainable gold income"):
        troops.queue_training(db_session, city, "basic_infantry", max_basic + 1)

    db_session.refresh(city)
    assert db_session.query(models.TroopQueue).filter_by(city_id=city.id).count() == 0
    for resource, amount in before.items():
        assert getattr(city, resource) == pytest.approx(amount)


def test_city_status_exposes_gross_net_and_upkeep_contract(
    client, db_session, city, user, monkeypatch
):
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)
    city.last_production = FIXED_NOW
    db_session.add(models.Troop(city_id=city.id, unit_type="basic_infantry", quantity=50))
    db_session.commit()

    response = client.get(
        f"/city/{city.id}/status",
        params={"world_id": city.world_id},
        headers=_headers(user),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gross_production_per_hour"]["gold"] == pytest.approx(8.0)
    assert payload["upkeep_used_per_hour"] == pytest.approx(1.0)
    assert payload["upkeep_reserved_per_hour"] == pytest.approx(0.0)
    assert payload["upkeep_capacity_per_hour"] == pytest.approx(8.0)
    assert payload["upkeep_available_per_hour"] == pytest.approx(7.0)
    assert payload["net_gold_per_hour"] == pytest.approx(7.0)
    assert payload["production_per_hour"]["gold"] == pytest.approx(7.0)
    assert payload["upkeep_sustainable"] is True

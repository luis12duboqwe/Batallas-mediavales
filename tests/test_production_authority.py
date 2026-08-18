from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.routers.auth import create_access_token
from app.services import economy, production


FIXED_NOW = datetime(2026, 8, 18, 18, 0, tzinfo=timezone.utc)


def _freeze_time(monkeypatch):
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)


def _auth_headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def test_one_hour_produces_exact_hourly_rate(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    city.wood = city.clay = city.iron = 0.0
    city.loyalty = 50.0
    city.last_production = FIXED_NOW - timedelta(hours=1)
    db_session.commit()

    updated, gains = production.recalculate_resources(
        db_session,
        city,
        return_gains=True,
        commit=False,
    )

    assert gains == pytest.approx({"wood": 15.0, "clay": 12.0, "iron": 10.0})
    assert updated.wood == pytest.approx(15.0)
    assert updated.clay == pytest.approx(12.0)
    assert updated.iron == pytest.approx(10.0)
    assert updated.loyalty == pytest.approx(52.0)
    assert updated.last_production == FIXED_NOW


def test_one_minute_is_one_sixtieth_of_hourly_rate(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    city.wood = city.clay = city.iron = 0.0
    city.last_production = FIXED_NOW - timedelta(minutes=1)
    db_session.commit()

    _, gains = production.recalculate_resources(
        db_session,
        city,
        return_gains=True,
        commit=False,
    )

    assert gains["wood"] == pytest.approx(15.0 / 60.0)
    assert gains["clay"] == pytest.approx(12.0 / 60.0)
    assert gains["iron"] == pytest.approx(10.0 / 60.0)


def test_world_resource_modifier_scales_hourly_rates(db_session, city):
    city.world.resource_modifier = 2.0
    db_session.commit()

    rates = production.get_production_per_hour(db_session, city)

    assert rates == pytest.approx({"wood": 30.0, "clay": 24.0, "iron": 20.0})


def test_warehouse_is_the_single_storage_formula(db_session, city):
    assert production.get_storage_limit(city) == economy.get_storage_capacity(0) == 5000.0

    warehouse = models.Building(city_id=city.id, name="warehouse", level=3)
    db_session.add(warehouse)
    db_session.commit()
    db_session.expire(city, ["buildings"])

    assert production.get_storage_limit(city) == 11000.0
    assert production.get_storage_limit(city) == economy.get_storage_capacity(3)


def test_production_stops_at_storage_without_destroying_overflow(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    city.wood = 4999.0
    city.clay = 6000.0  # Legacy/admin overflow must not be deleted by a tick.
    city.iron = 0.0
    city.last_production = FIXED_NOW - timedelta(hours=1)
    db_session.commit()

    updated, gains = production.recalculate_resources(
        db_session,
        city,
        return_gains=True,
        commit=False,
    )

    assert updated.wood == 5000.0
    assert gains["wood"] == 1.0
    assert updated.clay == 6000.0
    assert gains["clay"] == 0.0
    assert updated.iron == 10.0


def test_city_status_exposes_server_storage_and_hourly_rates(client, db_session, city, user):
    warehouse = models.Building(city_id=city.id, name="warehouse", level=2)
    db_session.add(warehouse)
    db_session.commit()

    response = client.get(
        f"/city/{city.id}/status",
        params={"world_id": city.world_id},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["storage_limit"] == 9000.0
    assert payload["production_per_hour"] == pytest.approx(
        {"wood": 15.0, "clay": 12.0, "iron": 10.0}
    )

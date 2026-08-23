from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.routers.auth import create_access_token
from app.services import balance, production, research, troops, unit_catalog


FIXED_NOW = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)


def _freeze_time(monkeypatch):
    monkeypatch.setattr(production, "utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(troops, "utc_now", lambda: FIXED_NOW)


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _auth_headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _set_resources(city: models.City, amount: float) -> None:
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, amount)


def _prepare_heavy_infantry_city(db_session, city):
    db_session.add_all(
        [
            models.Building(city_id=city.id, name="barracks", level=3),
            models.Building(city_id=city.id, name="smithy", level=1),
        ]
    )
    _set_resources(city, 5000.0)
    city.last_production = FIXED_NOW
    db_session.commit()
    db_session.refresh(city)


def test_available_catalog_matches_research_and_training_payment(
    db_session, city, monkeypatch
):
    _freeze_time(monkeypatch)
    _prepare_heavy_infantry_city(db_session, city)

    before_catalog = unit_catalog.get_availability(db_session, city)
    heavy = next(unit for unit in before_catalog if unit["unit_type"] == "heavy_infantry")
    assert heavy["research_cost"] == pytest.approx(
        {"wood": 500.0, "stone": 400.0, "iron": 300.0}
    )
    assert heavy["can_research"] is True

    before_research = {
        resource: float(getattr(city, resource))
        for resource in balance.RESOURCE_FIELDS
    }
    row = research.research_tech(db_session, city, "heavy_infantry")
    assert row.tech_name == "heavy_infantry"

    db_session.refresh(city)
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(city, resource) == pytest.approx(
            before_research[resource] - heavy["research_cost"].get(resource, 0.0)
        )
    assert "heavy_infantry" in city.researched_units
    assert (
        db_session.query(models.Research)
        .filter_by(city_id=city.id, tech_name="heavy_infantry")
        .count()
        == 1
    )

    after_catalog = unit_catalog.get_availability(db_session, city)
    heavy = next(unit for unit in after_catalog if unit["unit_type"] == "heavy_infantry")
    assert heavy["researched"] is True
    assert heavy["training_cost"] == pytest.approx(
        {"wood": 70.0, "stone": 60.0, "iron": 50.0}
    )

    before_training = {
        resource: float(getattr(city, resource))
        for resource in balance.RESOURCE_FIELDS
    }
    queue = troops.queue_training(db_session, city, "heavy_infantry", 2)
    expected_paid = {
        resource: amount * 2
        for resource, amount in heavy["training_cost"].items()
    }
    assert queue.paid_cost == pytest.approx(expected_paid)
    assert (_aware(queue.finish_time) - FIXED_NOW).total_seconds() == pytest.approx(
        heavy["training_time_seconds"] * 2
    )
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(city, resource) == pytest.approx(
            before_training[resource] - expected_paid.get(resource, 0.0)
        )


def test_research_sync_preserves_legacy_json_progress(db_session, city):
    city.researched_units = ["basic_infantry", "spy"]
    db_session.add(models.Research(city_id=city.id, tech_name="heavy_infantry", level=1))
    db_session.commit()

    research._sync_city_researched_units(db_session, city)
    db_session.commit()
    db_session.refresh(city)

    assert city.researched_units == ["basic_infantry", "spy", "heavy_infantry"]


def test_unit_availability_endpoint_exposes_server_quote(
    client, db_session, city, user, monkeypatch
):
    _freeze_time(monkeypatch)
    _prepare_heavy_infantry_city(db_session, city)

    response = client.get(
        "/troop/available",
        params={"city_id": city.id, "world_id": city.world_id},
        headers=_auth_headers(user),
    )
    assert response.status_code == 200
    heavy = next(
        unit for unit in response.json() if unit["unit_type"] == "heavy_infantry"
    )
    assert heavy["research_cost"] == {
        "wood": 500.0,
        "stone": 400.0,
        "iron": 300.0,
    }
    assert heavy["training_cost"] == {
        "wood": 70.0,
        "stone": 60.0,
        "iron": 50.0,
    }
    assert heavy["research_requirements_met"] is True
    assert heavy["can_research"] is True


def test_cancel_training_refunds_exact_persisted_payment(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    _set_resources(city, 100.0)
    city.last_production = FIXED_NOW
    paid_cost = {"wood": 111.0, "stone": 222.0, "iron": 333.0}
    queue = models.TroopQueue(
        city_id=city.id,
        troop_type="basic_infantry",
        amount=99,
        finish_time=FIXED_NOW + timedelta(hours=1),
        paid_cost=paid_cost,
    )
    db_session.add(queue)
    db_session.commit()
    queue_id = queue.id

    assert troops.cancel_troop_queue(db_session, queue_id, city.owner_id) is True

    db_session.refresh(city)
    for resource in balance.RESOURCE_FIELDS:
        expected = 100.0 + paid_cost.get(resource, 0.0) * troops.REFUND_FACTOR
        assert getattr(city, resource) == pytest.approx(expected)
    assert db_session.query(models.TroopQueue).filter_by(id=queue_id).first() is None


def test_due_training_cannot_be_cancelled(db_session, city, monkeypatch):
    _freeze_time(monkeypatch)
    _set_resources(city, 100.0)
    city.last_production = FIXED_NOW
    queue = models.TroopQueue(
        city_id=city.id,
        troop_type="basic_infantry",
        amount=1,
        finish_time=FIXED_NOW,
        paid_cost={"wood": 50.0, "stone": 30.0, "iron": 20.0},
    )
    db_session.add(queue)
    db_session.commit()

    with pytest.raises(ValueError, match="can no longer be cancelled"):
        troops.cancel_troop_queue(db_session, queue.id, city.owner_id)

    db_session.expire_all()
    assert db_session.query(models.TroopQueue).filter_by(id=queue.id).first() is not None


def test_training_completion_deletes_queue_before_side_effects(
    db_session, city, monkeypatch
):
    _freeze_time(monkeypatch)
    queue = models.TroopQueue(
        city_id=city.id,
        troop_type="basic_infantry",
        amount=3,
        finish_time=FIXED_NOW - timedelta(seconds=1),
        paid_cost={"wood": 150.0, "stone": 90.0, "iron": 60.0},
    )
    db_session.add(queue)
    db_session.commit()

    observed = {}

    def side_effect(session, info):
        observed["queue_count"] = session.query(models.TroopQueue).count()
        observed["quantity"] = (
            session.query(models.Troop)
            .filter_by(city_id=city.id, unit_type="basic_infantry")
            .one()
            .quantity
        )

    monkeypatch.setattr(troops, "_run_training_side_effects", side_effect)
    finished = troops.process_troop_queues(db_session)

    assert finished == [
        {"city_id": city.id, "troop_type": "basic_infantry", "amount": 3}
    ]
    assert observed == {"queue_count": 0, "quantity": 3}

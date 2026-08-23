from datetime import timedelta

import pytest

from app import models
from app.routers.auth import create_access_token
from app.seed import DEFAULT_WORLD_NAME, seed_game
from app.services import balance, building, combat, movement, troops
from app.utils import utc_now


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _assert_paid_from_starting_balance(
    city: models.City,
    *,
    starting: dict[str, float],
    costs: list[dict[str, float]],
) -> None:
    """Allow only the tiny server-authoritative production accrued in CI."""

    for resource in balance.RESOURCE_FIELDS:
        expected_after_costs = starting[resource] - sum(
            cost.get(resource, 0.0) for cost in costs
        )
        actual = float(getattr(city, resource))
        assert actual >= expected_after_costs
        assert actual < expected_after_costs + 1.0
        assert actual >= 0


def test_seeded_first_session_completes_without_admin_or_extra_resources(
    client, db_session, user, monkeypatch
):
    """Exercise the real initial economy through a likely first-attack defeat.

    The test may fast-forward durable timers, but it never grants resources,
    troops, buildings or tutorial progress. Every purchase is paid from the
    starting city's normal 500/500/500/500 resources and the target comes from
    the canonical seed.
    """

    seed_game(db_session)
    world = db_session.query(models.World).filter_by(name=DEFAULT_WORLD_NAME).one()
    headers = _headers(user)

    joined = client.post(f"/worlds/{world.id}/join", headers=headers)
    assert joined.status_code == 200, joined.text

    db_session.expire_all()
    city = (
        db_session.query(models.City)
        .filter_by(owner_id=user.id, world_id=world.id)
        .one()
    )
    starting = {
        resource: float(getattr(city, resource))
        for resource in balance.RESOURCE_FIELDS
    }
    assert starting == balance.CITY_STARTING_RESOURCES

    barracks_cost = balance.get_building_cost("barracks", 1)
    infantry_cost = balance.UNIT_CATALOG["basic_infantry"]["training_cost"]
    for resource in balance.RESOURCE_FIELDS:
        required = barracks_cost.get(resource, 0.0) + infantry_cost.get(resource, 0.0)
        assert starting[resource] >= required

    upgrade = client.post(
        "/building/upgrade",
        params={"world_id": world.id},
        json={"city_id": city.id, "building_type": "barracks"},
        headers=headers,
    )
    assert upgrade.status_code == 200, upgrade.text

    db_session.expire_all()
    city = db_session.query(models.City).filter_by(id=city.id).one()
    _assert_paid_from_starting_balance(
        city,
        starting=starting,
        costs=[barracks_cost],
    )

    building_queue = db_session.query(models.BuildingQueue).filter_by(id=upgrade.json()["id"]).one()
    building_queue.finish_time = utc_now() - timedelta(seconds=1)
    db_session.add(building_queue)
    db_session.commit()
    building.process_building_queues(db_session)

    train = client.post(
        "/troop/train",
        params={"world_id": world.id},
        json={"city_id": city.id, "troop_type": "basic_infantry", "amount": 1},
        headers=headers,
    )
    assert train.status_code == 200, train.text

    db_session.expire_all()
    city = db_session.query(models.City).filter_by(id=city.id).one()
    _assert_paid_from_starting_balance(
        city,
        starting=starting,
        costs=[barracks_cost, infantry_cost],
    )

    troop_queue = db_session.query(models.TroopQueue).filter_by(id=train.json()["id"]).one()
    troop_queue.finish_time = utc_now() - timedelta(seconds=1)
    db_session.add(troop_queue)
    db_session.commit()
    troops.process_troop_queues(db_session)

    barbarian = (
        db_session.query(models.City)
        .filter(
            models.City.world_id == world.id,
            models.City.owner_id.is_(None),
        )
        .order_by(models.City.id.asc())
        .first()
    )
    assert barbarian is not None
    assert sum(int(troop.quantity) for troop in barbarian.troops) > 1

    monkeypatch.setattr(combat, "_luck", lambda: 0.0)
    monkeypatch.setattr(movement, "_run_dispatch_side_effects", lambda *args, **kwargs: None)
    monkeypatch.setattr(movement, "_run_resolution_effect", lambda *args, **kwargs: None)

    attack = client.post(
        "/movement/",
        json={
            "origin_city_id": city.id,
            "target_city_id": barbarian.id,
            "movement_type": "attack",
            "troops": {"basic_infantry": 1},
            "resources": {},
            "spy_count": 0,
            "world_id": world.id,
        },
        headers=headers,
    )
    assert attack.status_code == 200, attack.text

    outgoing = db_session.query(models.Movement).filter_by(id=attack.json()["id"]).one()
    outgoing.arrival_time = utc_now() - timedelta(seconds=1)
    db_session.add(outgoing)
    db_session.commit()
    movement.resolve_due_movements(db_session)

    db_session.expire_all()
    assert (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type="basic_infantry")
        .one()
        .quantity
        == 0
    )
    assert (
        db_session.query(models.Movement)
        .filter(
            models.Movement.target_city_id == city.id,
            models.Movement.movement_type == "return",
            models.Movement.status == "ongoing",
        )
        .count()
        == 0
    )

    status = client.get("/tutorial/status", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["step"] == 7
    assert status.json()["completed"] is True
    assert status.json()["reward_claimed"] is False

    claim = client.post("/tutorial/advance", json={"step": 7}, headers=headers)
    assert claim.status_code == 200, claim.text
    assert claim.json()["completed"] is True
    assert claim.json()["reward_claimed"] is True
    for resource, expected in balance.TUTORIAL_REWARD.items():
        assert claim.json()["reward_granted_now"][resource] == pytest.approx(expected)

    db_session.expire_all()
    city = db_session.query(models.City).filter_by(id=city.id).one()
    for resource in balance.RESOURCE_FIELDS:
        assert float(getattr(city, resource)) >= 0

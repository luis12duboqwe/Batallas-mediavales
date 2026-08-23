from datetime import datetime, timedelta, timezone

from app import models
from app.routers.auth import create_access_token
from app.services import balance, building, combat, movement, troops


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {
            "sub": user.username,
            "type": "access",
            "ver": user.auth_version,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _tutorial(client, headers):
    response = client.get("/tutorial/status", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_g2_new_player_vertical_slice_end_to_end(
    client, db_session, user, monkeypatch
):
    """Exercise the accepted alpha journey without admin intervention."""

    headers = _headers(user)
    world = db_session.query(models.World).first()

    # A client cannot manufacture tutorial progress by sending an arbitrary step.
    forged = client.post(
        "/tutorial/advance",
        json={"step": 999},
        headers=headers,
    )
    assert forged.status_code == 200
    assert forged.json()["step"] == 0

    joined = client.post(f"/worlds/{world.id}/join", headers=headers)
    assert joined.status_code == 200, joined.text

    active_world = client.get("/worlds/active", headers=headers)
    assert active_world.status_code == 200, active_world.text
    snapshot = active_world.json()
    assert snapshot["current_world_id"] == world.id
    assert world.id in {item["id"] for item in snapshot["worlds"]}

    db_session.expire_all()
    city = (
        db_session.query(models.City)
        .filter_by(owner_id=user.id, world_id=world.id)
        .one()
    )
    assert _tutorial(client, headers)["step"] == 1

    barbarian = models.City(
        name="Tutorial Barbarian",
        owner_id=None,
        world_id=world.id,
        x=city.x + 3,
        y=city.y,
        wood=120.0,
        stone=120.0,
        iron=120.0,
        gold=120.0,
        loyalty=100.0,
    )
    db_session.add(barbarian)
    db_session.commit()

    upgrade = client.post(
        "/building/upgrade",
        params={"world_id": world.id},
        json={"city_id": city.id, "building_type": "barracks"},
        headers=headers,
    )
    assert upgrade.status_code == 200, upgrade.text
    queue = db_session.query(models.BuildingQueue).filter_by(id=upgrade.json()["id"]).one()
    queue.finish_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.add(queue)
    db_session.commit()
    building.process_building_queues(db_session)
    assert _tutorial(client, headers)["step"] == 2

    train = client.post(
        "/troop/train",
        params={"world_id": world.id},
        json={"city_id": city.id, "troop_type": "basic_infantry", "amount": 1},
        headers=headers,
    )
    assert train.status_code == 200, train.text
    troop_queue = db_session.query(models.TroopQueue).filter_by(id=train.json()["id"]).one()
    troop_queue.finish_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.add(troop_queue)
    db_session.commit()
    troops.process_troop_queues(db_session)
    assert _tutorial(client, headers)["step"] == 4

    user.protection_ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add(user)
    db_session.commit()
    monkeypatch.setattr(combat, "_luck", lambda: 0.0)
    monkeypatch.setattr(
        movement,
        "_run_dispatch_side_effects",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        movement,
        "_run_resolution_effect",
        lambda *args, **kwargs: None,
    )

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
    assert _tutorial(client, headers)["step"] == 5

    outgoing = db_session.query(models.Movement).filter_by(id=attack.json()["id"]).one()
    outgoing.arrival_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.add(outgoing)
    db_session.commit()
    movement.resolve_due_movements(db_session)
    assert _tutorial(client, headers)["step"] == 6

    return_move = (
        db_session.query(models.Movement)
        .filter_by(target_city_id=city.id, movement_type="return", status="ongoing")
        .one()
    )
    return_move.arrival_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.add(return_move)
    db_session.commit()
    movement.resolve_due_movements(db_session)

    before_reward = {
        resource: float(getattr(db_session.query(models.City).filter_by(id=city.id).one(), resource))
        for resource in balance.RESOURCE_FIELDS
    }

    # GET is read-only: it may discover completion but never performs a reward write.
    completed_read = _tutorial(client, headers)
    assert completed_read["step"] == 7
    assert completed_read["completed"] is True
    assert completed_read["reward_claimed"] is False

    claim = client.post(
        "/tutorial/advance",
        json={"step": 999},
        headers=headers,
    )
    assert claim.status_code == 200, claim.text
    completed = claim.json()
    assert completed["step"] == 7
    assert completed["completed"] is True
    assert completed["reward_claimed"] is True
    assert completed["reward"] == balance.TUTORIAL_REWARD

    db_session.expire_all()
    after_first = db_session.query(models.City).filter_by(id=city.id).one()
    first_balances = {
        resource: float(getattr(after_first, resource))
        for resource in balance.RESOURCE_FIELDS
    }
    for resource in first_balances:
        assert first_balances[resource] >= before_reward[resource]

    repeated = client.post(
        "/tutorial/advance",
        json={"step": 7},
        headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["reward_granted_now"] == {}
    assert _tutorial(client, headers)["reward_claimed"] is True

    db_session.expire_all()
    after_second = db_session.query(models.City).filter_by(id=city.id).one()
    assert {
        resource: float(getattr(after_second, resource))
        for resource in balance.RESOURCE_FIELDS
    } == first_balances

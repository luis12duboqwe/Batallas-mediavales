import json

from app import models
from app.routers.auth import create_access_token
from app.services import world_lifecycle


def _auth_headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    return {"Authorization": f"Bearer {token}"}


def test_admin_created_world_defaults_to_draft_and_cannot_be_joined(
    client, db_session, user
):
    user.is_admin = True
    db_session.commit()

    created = client.post(
        "/worlds/create",
        headers=_auth_headers(user),
        json={
            "name": "BM0072 Draft",
            "speed_modifier": 1.0,
            "resource_modifier": 1.0,
            "map_size": 25,
            "special_rules": "",
        },
    )
    assert created.status_code == 200, created.text
    world = created.json()
    assert world["lifecycle_status"] == "draft"
    assert world["is_active"] is False

    joined = client.post(f"/worlds/{world['id']}/join", headers=_auth_headers(user))
    assert joined.status_code == 404


def test_lifecycle_transition_is_audited_and_preserves_world_data(
    db_session, user, city
):
    user.is_admin = True
    city.name = "Preserved BM0072 City"
    city.world.lifecycle_status = "open"
    city.world.is_active = True
    db_session.commit()
    world_id = city.world_id

    paused = world_lifecycle.transition_world(
        db_session,
        world_id,
        target_status="paused",
        reason="Maintenance window",
        admin_user=user,
    )
    assert paused.lifecycle_status == "paused"
    assert paused.is_active is False
    assert paused.pause_started_at is not None

    reopened = world_lifecycle.transition_world(
        db_session,
        world_id,
        target_status="open",
        reason="Maintenance complete",
        admin_user=user,
    )
    assert reopened.lifecycle_status == "open"
    assert reopened.is_active is True
    assert reopened.pause_started_at is None

    closed = world_lifecycle.transition_world(
        db_session,
        world_id,
        target_status="closed",
        reason="Season completed",
        admin_user=user,
    )
    ended_at = closed.ended_at
    assert ended_at is not None

    archived = world_lifecycle.transition_world(
        db_session,
        world_id,
        target_status="archived",
        reason="Move to historical catalogue",
        admin_user=user,
    )
    assert archived.lifecycle_status == "archived"
    assert archived.ended_at == ended_at
    assert db_session.query(models.City).filter_by(id=city.id).one().name == "Preserved BM0072 City"

    logs = (
        db_session.query(models.Log)
        .filter_by(user_id=user.id, action="world_lifecycle_transition")
        .order_by(models.Log.id.asc())
        .all()
    )
    assert [json.loads(entry.details)["to_status"] for entry in logs] == [
        "paused",
        "open",
        "closed",
        "archived",
    ]


def test_invalid_transition_does_not_mutate_world(db_session, user, city):
    user.is_admin = True
    city.world.lifecycle_status = "open"
    city.world.is_active = True
    db_session.commit()

    try:
        world_lifecycle.transition_world(
            db_session,
            city.world_id,
            target_status="archived",
            reason="Invalid jump",
            admin_user=user,
        )
    except Exception as exc:
        assert "Invalid world lifecycle transition" in str(exc)
    else:
        raise AssertionError("open -> archived must be rejected")

    db_session.refresh(city.world)
    assert city.world.lifecycle_status == "open"
    assert city.world.is_active is True

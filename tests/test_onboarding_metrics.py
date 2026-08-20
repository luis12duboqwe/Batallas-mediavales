from datetime import timedelta

from app import models
from app.routers.auth import create_access_token
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


def _player(db_session, *, username, email, step, completed, last_active_at):
    user = models.User(
        username=username,
        email=email,
        hashed_password="placeholder",
        is_verified=True,
        tutorial_step=step,
        tutorial_reward_claimed=completed,
        last_active_at=last_active_at,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_onboarding_metrics_are_admin_only(client, user):
    response = client.get("/admin/metrics/onboarding", headers=_headers(user))
    assert response.status_code == 403


def test_onboarding_metrics_are_aggregate_and_contain_no_pii(
    client, db_session, user
):
    now = utc_now()
    world = db_session.query(models.World).first()

    user.tutorial_step = 1
    user.tutorial_reward_claimed = False
    user.last_active_at = now

    stalled = _player(
        db_session,
        username="stalled-private-name",
        email="stalled-private@example.com",
        step=3,
        completed=False,
        last_active_at=now - timedelta(hours=48),
    )
    completed = _player(
        db_session,
        username="completed-private-name",
        email="completed-private@example.com",
        step=7,
        completed=True,
        last_active_at=now - timedelta(hours=48),
    )
    admin = _player(
        db_session,
        username="metrics-admin",
        email="metrics-admin@example.com",
        step=0,
        completed=False,
        last_active_at=now,
    )
    admin.is_admin = True

    db_session.add_all(
        [
            models.PlayerWorld(user_id=user.id, world_id=world.id),
            models.PlayerWorld(user_id=completed.id, world_id=world.id),
        ]
    )
    db_session.commit()

    response = client.get(
        "/admin/metrics/onboarding?window_hours=24",
        headers=_headers(admin),
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total_players"] == 3
    assert payload["joined_world"] == 2
    assert payload["tutorial_completed"] == 1
    assert payload["active_in_window"] == 1
    assert payload["inactive_incomplete"] == 1
    assert payload["join_rate"] == 2 / 3
    assert payload["completion_rate"] == 1 / 3
    assert payload["tutorial_step_counts"]["1"] == 1
    assert payload["tutorial_step_counts"]["3"] == 1
    assert payload["tutorial_step_counts"]["7"] == 1
    assert payload["inactive_incomplete_by_step"]["3"] == 1
    assert payload["reached_step_counts"]["0"] == 3
    assert payload["reached_step_counts"]["4"] == 1

    serialized = response.text
    for forbidden in (
        user.username,
        user.email,
        stalled.username,
        stalled.email,
        completed.username,
        completed.email,
        admin.username,
        admin.email,
    ):
        assert forbidden not in serialized

    assert set(payload) == {
        "window_hours",
        "total_players",
        "joined_world",
        "tutorial_completed",
        "active_in_window",
        "inactive_incomplete",
        "join_rate",
        "completion_rate",
        "tutorial_step_counts",
        "reached_step_counts",
        "inactive_incomplete_by_step",
    }

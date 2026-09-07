import pytest
from fastapi import HTTPException

from app import models
from app.routers.auth import create_access_token
from app.services import anticheat


def _headers(user: models.User) -> dict[str, str]:
    token = create_access_token(
        {"sub": user.username, "type": "access", "ver": user.auth_version}
    )
    return {"Authorization": f"Bearer {token}"}


def test_rate_limit_blocks_without_freezing_account(db_session, user):
    anticheat.enforce_action_rate_limit(
        db_session,
        user,
        "bm74.test",
        limit=2,
        window_seconds=60,
    )
    anticheat.enforce_action_rate_limit(
        db_session,
        user,
        "bm74.test",
        limit=2,
        window_seconds=60,
    )

    with pytest.raises(HTTPException) as exc_info:
        anticheat.enforce_action_rate_limit(
            db_session,
            user,
            "bm74.test",
            limit=2,
            window_seconds=60,
        )

    assert exc_info.value.status_code == 429
    assert int(exc_info.value.headers["Retry-After"]) >= 1

    db_session.expire_all()
    persisted = db_session.query(models.User).filter_by(id=user.id).one()
    bucket = (
        db_session.query(models.AntiCheatRateBucket)
        .filter_by(user_id=user.id, action_key="bm74.test")
        .one()
    )
    flags = (
        db_session.query(models.AntiCheatFlag)
        .filter_by(user_id=user.id, type_of_violation="rate_limit:bm74.test")
        .all()
    )
    assert persisted.is_frozen is False
    assert persisted.freeze_reason is None
    assert bucket.request_count == 2
    assert bucket.blocked_until is not None
    assert len(flags) == 1


def test_rate_limit_action_types_are_independent(db_session, user):
    anticheat.enforce_action_rate_limit(
        db_session,
        user,
        "bm74.action.a",
        limit=1,
        window_seconds=60,
    )
    anticheat.enforce_action_rate_limit(
        db_session,
        user,
        "bm74.action.b",
        limit=1,
        window_seconds=60,
    )

    buckets = (
        db_session.query(models.AntiCheatRateBucket)
        .filter(models.AntiCheatRateBucket.user_id == user.id)
        .all()
    )
    assert {(bucket.action_key, bucket.request_count) for bucket in buckets} == {
        ("bm74.action.a", 1),
        ("bm74.action.b", 1),
    }


def test_rate_limit_repeated_denials_dedupe_flags(db_session, user):
    anticheat.enforce_action_rate_limit(
        db_session,
        user,
        "bm74.dedupe",
        limit=1,
        window_seconds=60,
    )

    for _ in range(3):
        with pytest.raises(HTTPException) as exc_info:
            anticheat.enforce_action_rate_limit(
                db_session,
                user,
                "bm74.dedupe",
                limit=1,
                window_seconds=60,
            )
        assert exc_info.value.status_code == 429

    assert (
        db_session.query(models.AntiCheatFlag)
        .filter_by(user_id=user.id, type_of_violation="rate_limit:bm74.dedupe")
        .count()
        == 1
    )


def test_movement_endpoint_applies_authoritative_rate_limit(
    client,
    user,
    monkeypatch,
):
    monkeypatch.setitem(anticheat.RATE_LIMIT_RULES, "movement.create", (1, 60))
    payload = {
        "origin_city_id": 999999,
        "target_city_id": 999998,
        "movement_type": "attack",
        "troops": {"basic_infantry": 1},
        "resources": {},
        "world_id": 1,
    }

    first = client.post("/movement/", json=payload, headers=_headers(user))
    assert first.status_code == 404

    blocked = client.post("/movement/", json=payload, headers=_headers(user))
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Rate limit exceeded"
    assert int(blocked.headers["Retry-After"]) >= 1

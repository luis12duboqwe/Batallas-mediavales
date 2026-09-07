import pytest
from fastapi import HTTPException

from app import models
from app.services import anticheat


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

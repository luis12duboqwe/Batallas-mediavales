"""BM-0090: enforce exactly one active privacy case per owner and category."""

import pytest
from sqlalchemy.exc import IntegrityError

from app import models
from app.routers.account_data import PRIVACY_SUBJECTS
from app.routers.auth import create_access_token


def _headers(user):
    return {"Authorization": "Bearer " + create_access_token({
        "sub": user.username, "type": "access", "ver": user.auth_version,
    })}


def _case(owner_id, *, subject, status="open"):
    return models.SupportCase(
        requester_id=owner_id, subject=subject,
        description="Controlled privacy request test", status=status,
    )


@pytest.mark.parametrize("active_status", ["open", "in_progress"])
def test_active_privacy_duplicate_is_rejected_by_database(db_session, user, active_status):
    subject = PRIVACY_SUBJECTS["erasure"]
    db_session.add(_case(user.id, subject=subject, status=active_status))
    db_session.commit()

    db_session.add(_case(user.id, subject=subject, status="open"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.query(models.SupportCase).filter_by(
        requester_id=user.id, subject=subject,
    ).count() == 1


def test_privacy_uniqueness_preserves_closed_history_and_multiple_categories(client, db_session, user):
    subject = PRIVACY_SUBJECTS["rectification"]
    db_session.add(_case(user.id, subject=subject, status="resolved"))
    db_session.add(_case(user.id, subject=subject, status="closed"))
    db_session.commit()

    response = client.post(
        "/auth/me/privacy-requests", headers=_headers(user),
        json={"kind": "rectification", "details": "My correction"},
    )
    assert response.status_code == 200, response.text
    active_id = response.json()["id"]
    assert db_session.query(models.SupportCase).filter_by(
        requester_id=user.id, subject=subject,
    ).count() == 3

    duplicate = client.post(
        "/auth/me/privacy-requests", headers=_headers(user),
        json={"kind": "rectification", "details": "Duplicate"},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["id"] == active_id

    other_type = client.post(
        "/auth/me/privacy-requests", headers=_headers(user),
        json={"kind": "retention"},
    )
    assert other_type.status_code == 200
    assert other_type.json()["id"] != active_id


def test_unique_index_does_not_restrict_normal_support_or_other_accounts(db_session, user):
    second = models.User(
        username="bm90_unique_other", email="bm90_unique_other@example.com",
        hashed_password="placeholder", is_verified=True,
    )
    db_session.add(second)
    db_session.commit()

    rows = [
        _case(user.id, subject="General technical support"),
        _case(user.id, subject="General technical support"),
        _case(user.id, subject=PRIVACY_SUBJECTS["other"]),
        _case(second.id, subject=PRIVACY_SUBJECTS["other"]),
    ]
    db_session.add_all(rows)
    db_session.commit()

    assert db_session.query(models.SupportCase).count() == 4
    assert db_session.query(models.SupportCase).filter_by(
        requester_id=user.id, subject="General technical support",
    ).count() == 2


def test_privacy_uniqueness_rejects_status_transition_into_duplicate(db_session, user):
    subject = PRIVACY_SUBJECTS["retention"]
    db_session.add(_case(user.id, subject=subject, status="open"))
    db_session.add(_case(user.id, subject=subject, status="resolved"))
    db_session.commit()
    historical = db_session.query(models.SupportCase).filter_by(
        requester_id=user.id, subject=subject, status="resolved",
    ).one()
    historical.status = "in_progress"
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert db_session.query(models.SupportCase).filter_by(
        requester_id=user.id, subject=subject, status="open",
    ).count() == 1

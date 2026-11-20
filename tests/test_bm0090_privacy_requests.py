"""BM-0090: privacy request workflow without automatic destructive effects."""

from app import models
from app.routers.auth import create_access_token


def headers(user):
    return {
        "Authorization": "Bearer " + create_access_token({
            "sub": user.username, "type": "access", "ver": user.auth_version,
        })
    }


def other_user(db):
    opponent = models.User(
        username="bm90_opponent", email="bm90_opponent@example.com",
        hashed_password="placeholder", is_verified=True,
    )
    db.add(opponent)
    db.commit()
    db.refresh(opponent)
    return opponent


def test_privacy_request_requires_authenticated_current_account(client, db_session, user):
    assert client.post("/auth/me/privacy-requests", json={"kind": "erasure"}).status_code == 401
    assert client.get("/auth/me/privacy-requests").status_code == 401
    old = headers(user)
    user.auth_version += 1
    db_session.commit()
    assert client.post(
        "/auth/me/privacy-requests", json={"kind": "erasure"}, headers=old,
    ).status_code == 401
    assert client.get("/auth/me/privacy-requests", headers=old).status_code == 401

    created = client.post(
        "/auth/me/privacy-requests",
        json={"kind": "erasure", "details": " Revisión de mis datos  "},
        headers=headers(user),
    )
    assert created.status_code == 200, created.text
    assert created.headers["cache-control"] == "private, no-store"
    assert created.json()["status"] == "open"
    assert created.json()["kind"] == "erasure"
    case = db_session.get(models.SupportCase, created.json()["id"])
    assert case.requester_id == user.id
    assert case.world_id is None
    assert "Revisión de mis datos" in case.description
    assert "borrado" in case.description
    assert db_session.query(models.User).filter_by(id=user.id).one() is not None


def test_privacy_case_is_idempotent_when_open_and_reopens_after_resolution(client, db_session, user):
    first = client.post(
        "/auth/me/privacy-requests",
        json={"kind": "rectification", "details": "Corregir mi correo"},
        headers=headers(user),
    )
    again = client.post(
        "/auth/me/privacy-requests",
        json={"kind": "rectification", "details": "Intento duplicado"},
        headers=headers(user),
    )
    assert first.status_code == 200
    assert again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    assert db_session.query(models.SupportCase).count() == 1
    case = db_session.get(models.SupportCase, first.json()["id"])
    assert "Intento duplicado" not in case.description

    case.status = "resolved"
    case.resolution = "Reviewed by support"
    db_session.commit()
    again_after_resolution = client.post(
        "/auth/me/privacy-requests",
        json={"kind": "rectification"},
        headers=headers(user),
    )
    assert again_after_resolution.status_code == 200
    assert again_after_resolution.json()["id"] != first.json()["id"]
    assert db_session.query(models.SupportCase).count() == 2


def test_privacy_requests_scope_and_status_are_account_local(client, db_session, user):
    opponent = other_user(db_session)
    foreign = client.post(
        "/auth/me/privacy-requests",
        json={"kind": "retention", "details": "Never export this note to other user"},
        headers=headers(opponent),
    )
    assert foreign.status_code == 200
    own = client.post(
        "/auth/me/privacy-requests",
        json={"kind": "other", "details": "Own question"},
        headers=headers(user),
    )
    assert own.status_code == 200
    cases = client.get("/auth/me/privacy-requests", headers=headers(user))
    assert cases.status_code == 200
    assert cases.headers["cache-control"] == "private, no-store"
    assert [row["id"] for row in cases.json()] == [own.json()["id"]]
    assert "Never export this note" not in cases.text

    other_cases = client.get("/auth/me/privacy-requests", headers=headers(opponent))
    assert [row["id"] for row in other_cases.json()] == [foreign.json()["id"]]
    foreign_case = client.get(
        "/support/cases/" + str(foreign.json()["id"]), headers=headers(user),
    )
    assert foreign_case.status_code == 404


def test_privacy_request_rejects_invalid_and_spoofed_inputs(client, db_session, user):
    for invalid in [
        {"kind": "delete_now"}, {"kind": "erasure", "user_id": 999},
        {"kind": "erasure", "details": "x" * 1001},
        {"kind": "erasure", "details": None},
        {"kind": "erasure", "status": "resolved"},
    ]:
        assert client.post(
            "/auth/me/privacy-requests", json=invalid, headers=headers(user),
        ).status_code == 422
    assert db_session.query(models.SupportCase).count() == 0
    manual_spoof = client.post(
        "/support/cases",
        json={
            "subject": "[PRIVACY] Solicitud de eliminación de cuenta",
            "description": "Pretend this went through the review process",
        },
        headers=headers(user),
    )
    assert manual_spoof.status_code == 400
    assert db_session.query(models.SupportCase).count() == 0


def test_privacy_request_uses_existing_review_and_does_not_delete_account(client, db_session, user):
    created = client.post(
        "/auth/me/privacy-requests", json={"kind": "erasure"}, headers=headers(user),
    )
    assert created.status_code == 200
    case = db_session.get(models.SupportCase, created.json()["id"])
    assert case.status == "open"
    assert case.subject.startswith("[PRIVACY]")
    assert db_session.get(models.User, user.id) is not None
    user.is_frozen = True
    db_session.commit()
    assert client.post(
        "/auth/me/privacy-requests", json={"kind": "erasure"}, headers=headers(user),
    ).status_code == 403



def test_privacy_support_workflow_reflects_admin_review(client, db_session, user):
    operator = models.User(
        username="bm90_support", email="bm90_support@example.com",
        hashed_password="placeholder", is_verified=True,
        is_admin=True, admin_role="support",
    )
    db_session.add(operator)
    db_session.commit()
    created = client.post(
        "/auth/me/privacy-requests",
        json={"kind": "retention"},
        headers=headers(user),
    )
    assert created.status_code == 200
    case_id = created.json()["id"]
    admin_reply = client.patch(
        "/support/admin/cases/" + str(case_id),
        json={
            "status": "resolved",
            "resolution": "Revisión de soporte completada.",
            "reason": "Atención a solicitud del titular",
        },
        headers=headers(operator),
    )
    assert admin_reply.status_code == 200, admin_reply.text
    listing = client.get("/auth/me/privacy-requests", headers=headers(user))
    assert listing.status_code == 200
    assert listing.json()[0]["status"] == "resolved"
    assert listing.json()[0]["resolution"] == "Revisión de soporte completada."

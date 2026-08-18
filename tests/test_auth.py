from urllib.parse import parse_qs, urlparse

import httpx

from app import models
from app.routers.auth import get_password_hash
from app.services import emailer


PASSWORD = "Castle12345"


def _token_from_email_body(body: str) -> str:
    url = body.rsplit(" ", 1)[-1]
    token = parse_qs(urlparse(url).query).get("token", [None])[0]
    assert token
    return token


def test_register_verify_login_end_to_end(client: httpx.Client, db_session, monkeypatch):
    sent_messages = []

    def fake_send(to_email, subject, body):
        sent_messages.append((to_email, subject, body))
        return True

    monkeypatch.setattr(emailer, "send_email", fake_send)

    register_payload = {
        "username": "player1",
        "email": "player1@example.com",
        "password": PASSWORD,
        "email_notifications": False,
        "language": "en",
    }
    register_response = client.post("/auth/register", json=register_payload)
    assert register_response.status_code == 200
    assert register_response.json()["username"] == "player1"
    assert len(sent_messages) == 1

    # Login is forbidden until the exact verification token delivered by email
    # has been consumed.
    unverified_login = client.post(
        "/auth/token",
        data={"username": "player1", "password": PASSWORD},
    )
    assert unverified_login.status_code == 403

    verification_token = _token_from_email_body(sent_messages[0][2])
    verify_response = client.post(
        "/auth/verify-email",
        params={"token": verification_token},
    )
    assert verify_response.status_code == 200

    # Verification tokens are one-time.
    second_verify = client.post(
        "/auth/verify-email",
        params={"token": verification_token},
    )
    assert second_verify.status_code == 400

    token_resp = client.post(
        "/auth/token",
        data={"username": "player1", "password": PASSWORD},
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    auth_header = {"Authorization": f"Bearer {token_data['access_token']}"}

    me_resp = client.get("/auth/me", headers=auth_header)
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "player1"

    # A purpose-limited verification JWT can never be used as an access token.
    purpose_confusion = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {verification_token}"},
    )
    assert purpose_confusion.status_code == 401

    user = db_session.query(models.User).filter(models.User.username == "player1").one()
    assert user.is_verified is True
    assert user.verification_token is None


def test_registration_rejects_weak_password(client: httpx.Client):
    response = client.post(
        "/auth/register",
        json={
            "username": "weak-user",
            "email": "weak@example.com",
            "password": "short1",
        },
    )
    assert response.status_code == 422


def test_frozen_user_cannot_login_or_reuse_existing_http_session(client, db_session):
    user = models.User(
        username="frozen-player",
        email="frozen@example.com",
        hashed_password=get_password_hash(PASSWORD),
        is_verified=True,
        is_frozen=False,
    )
    db_session.add(user)
    db_session.commit()

    login = client.post(
        "/auth/token",
        data={"username": user.username, "password": PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    user.is_frozen = True
    user.freeze_reason = "security review"
    db_session.commit()

    protected = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert protected.status_code == 403

    second_login = client.post(
        "/auth/token",
        data={"username": user.username, "password": PASSWORD},
    )
    assert second_login.status_code == 403

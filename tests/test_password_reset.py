from urllib.parse import parse_qs, urlparse

from app import models
from app.routers.auth import get_password_hash
from app.services import emailer


OLD_PASSWORD = "OldCastle123"
NEW_PASSWORD = "NewCastle456"


def _token_from_email_body(body: str) -> str:
    url = body.rsplit(" ", 1)[-1]
    token = parse_qs(urlparse(url).query).get("token", [None])[0]
    assert token
    return token


def test_password_reset_flow_is_end_to_end_and_one_time(client, db_session, monkeypatch):
    sent_messages = []

    def fake_send(to_email, subject, body):
        sent_messages.append((to_email, subject, body))
        return True

    monkeypatch.setattr(emailer, "send_email", fake_send)

    user = models.User(
        username="reset_user",
        email="reset@example.com",
        hashed_password=get_password_hash(OLD_PASSWORD),
        email_notifications=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    old_login = client.post(
        "/auth/token",
        data={"username": user.username, "password": OLD_PASSWORD},
    )
    assert old_login.status_code == 200
    old_access_token = old_login.json()["access_token"]

    response = client.post("/auth/forgot-password", json={"email": user.email})
    assert response.status_code == 200
    assert response.json()["message"] == "If the email exists, a reset link has been sent."
    assert len(sent_messages) == 1

    reset_token = _token_from_email_body(sent_messages[0][2])

    # Reset-purpose JWTs are not accepted by normal protected HTTP routes.
    wrong_purpose = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {reset_token}"},
    )
    assert wrong_purpose.status_code == 401

    response = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200

    # The stored reset token is cleared after one successful use.
    second_use = client.post(
        "/auth/reset-password",
        json={"token": reset_token, "new_password": "AnotherCastle789"},
    )
    assert second_use.status_code == 400

    # Password reset invalidates all previously issued access tokens.
    stale_session = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {old_access_token}"},
    )
    assert stale_session.status_code == 401

    new_login = client.post(
        "/auth/token",
        data={"username": user.username, "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200

    old_password_login = client.post(
        "/auth/token",
        data={"username": user.username, "password": OLD_PASSWORD},
    )
    assert old_password_login.status_code == 401


def test_password_reset_invalid_token(client):
    response = client.post(
        "/auth/reset-password",
        json={"token": "invalid_token", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400


def test_forgot_password_does_not_reveal_unknown_email(client, monkeypatch):
    calls = []
    monkeypatch.setattr(emailer, "send_email", lambda *args: calls.append(args) or True)

    response = client.post(
        "/auth/forgot-password",
        json={"email": "does-not-exist@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "If the email exists, a reset link has been sent."
    assert calls == []

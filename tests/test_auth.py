import httpx
from app import models


def test_register_and_login(client: httpx.Client, db_session):
    register_payload = {
        "username": "player1",
        "email": "player1@example.com",
        "password": "secret123",
        "email_notifications": False,
        "language": "en",
    }
    register_response = client.post("/auth/register", json=register_payload)
    assert register_response.status_code == 200
    data = register_response.json()
    assert data["username"] == "player1"

    # Get verification token from DB
    user = db_session.query(models.User).filter(models.User.username == "player1").first()
    assert user is not None
    assert user.verification_token is not None
    
    # Verify email
    verify_response = client.post(f"/auth/verify-email?token={user.verification_token}")
    assert verify_response.status_code == 200

    token_resp = client.post(
        "/auth/token",
        data={"username": "player1", "password": "secret123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert "access_token" in token_data
    auth_header = {"Authorization": f"Bearer {token_data['access_token']}"}
    me_resp = client.get("/auth/me", headers=auth_header)
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "player1"

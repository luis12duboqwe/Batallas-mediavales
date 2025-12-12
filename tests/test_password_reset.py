from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models, schemas
from app.main import app
from app.routers.auth import create_access_token
from datetime import timedelta

client = TestClient(app)

def test_password_reset_flow(db_session: Session):
    # 1. Create user
    user = models.User(
        username="reset_user",
        email="reset@example.com",
        hashed_password="oldpassword",
        email_notifications=True
    )
    db_session.add(user)
    db_session.commit()
    
    # 2. Request password reset
    response = client.post("/auth/forgot-password", json={"email": "reset@example.com"})
    assert response.status_code == 200
    assert response.json()["message"] == "If the email exists, a reset link has been sent."
    
    # 3. Generate a valid token manually (since we can't intercept the email in this test easily without mocking)
    # In a real integration test, we'd mock the emailer.
    reset_token = create_access_token(
        data={"sub": user.username, "type": "reset"},
        expires_delta=timedelta(minutes=15)
    )
    
    # 4. Reset password
    new_password = "newpassword123"
    response = client.post("/auth/reset-password", json={
        "token": reset_token,
        "new_password": new_password
    })
    assert response.status_code == 200
    assert response.json()["message"] == "Password updated successfully"
    
    # 5. Verify login with new password
    response = client.post("/auth/token", data={
        "username": "reset_user",
        "password": new_password
    })
    assert response.status_code == 200
    assert "access_token" in response.json()
    
    # 6. Verify old password fails
    response = client.post("/auth/token", data={
        "username": "reset_user",
        "password": "oldpassword"
    })
    assert response.status_code == 401

def test_password_reset_invalid_token(db_session: Session):
    response = client.post("/auth/reset-password", json={
        "token": "invalid_token",
        "new_password": "newpassword"
    })
    assert response.status_code == 400 # Or 401 depending on implementation, auth.py raises 400 for invalid token

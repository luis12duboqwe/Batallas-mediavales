from app import models
from app.main import app
from app.routers.auth import get_current_user

def test_tutorial_flow(client, db_session, user):
    app.dependency_overrides[get_current_user] = lambda: user

    # 1. Check initial status
    response = client.get("/tutorial/status")
    assert response.status_code == 200
    assert response.json()["step"] == 0

    # 2. Advance step
    response = client.post("/tutorial/advance", json={"step": 1})
    assert response.status_code == 200
    assert response.json()["step"] == 1

    # 3. Check status again
    response = client.get("/tutorial/status")
    assert response.json()["step"] == 1

    # 4. Try to go back (should fail or stay same)
    response = client.post("/tutorial/advance", json={"step": 0})
    assert response.status_code == 200
    assert response.json()["step"] == 1 # Should not regress
    
    app.dependency_overrides.pop(get_current_user)

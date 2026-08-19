from app import models
from app.main import app
from app.routers.auth import get_current_user


def test_tutorial_flow_is_server_authoritative(client, db_session, user):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        # No durable game progress exists yet.
        response = client.get("/tutorial/status")
        assert response.status_code == 200
        assert response.json()["step"] == 0

        # Client-supplied steps are backwards-compatible input only; they never
        # manufacture progress, even when jumping far ahead.
        response = client.post("/tutorial/advance", json={"step": 1})
        assert response.status_code == 200
        assert response.json()["step"] == 0

        response = client.post("/tutorial/advance", json={"step": 999})
        assert response.status_code == 200
        assert response.json()["step"] == 0

        # Once durable state exists, the server derives the next step itself.
        world = db_session.query(models.World).first()
        city = models.City(
            name="Tutorial Capital",
            owner_id=user.id,
            world_id=world.id,
            x=20,
            y=20,
        )
        user.world_id = world.id
        db_session.add_all([city, user])
        db_session.commit()

        response = client.get("/tutorial/status")
        assert response.status_code == 200
        assert response.json()["step"] == 1

        # Asking to go backwards or forwards cannot override derived progress.
        response = client.post("/tutorial/advance", json={"step": 0})
        assert response.status_code == 200
        assert response.json()["step"] == 1
        response = client.post("/tutorial/advance", json={"step": 7})
        assert response.status_code == 200
        assert response.json()["step"] == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)

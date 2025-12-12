import os
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.database import Base, engine, SessionLocal, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402


def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def create_world(db):
    world = models.World(name="TestWorld", speed_modifier=1.0, resource_modifier=1.0)
    db.add(world)
    db.commit()
    db.refresh(world)
    return world


@pytest.fixture()
def db_session():
    setup_database()
    db = SessionLocal()
    try:
        create_world(db)
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def user(db_session):
    user = models.User(
        username="tester",
        email="tester@example.com",
        hashed_password="placeholder",
        protection_ends_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def city(db_session, user):
    world = db_session.query(models.World).first()
    city = models.City(name="Capital", owner_id=user.id, world_id=world.id, x=0, y=0)
    db_session.add(city)
    db_session.commit()
    db_session.refresh(city)
    return city


@pytest.fixture()
def second_city(db_session, user):
    world = db_session.query(models.World).first()
    city = models.City(name="Frontier", owner_id=user.id, world_id=world.id, x=3, y=4)
    db_session.add(city)
    db_session.commit()
    db_session.refresh(city)
    return city

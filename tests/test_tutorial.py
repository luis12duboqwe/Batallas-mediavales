import json
from datetime import timedelta

from app import models
from app.main import app
from app.routers.auth import get_current_user
from app.services import tutorial
from app.utils import utc_now


def test_tutorial_flow_is_server_authoritative(client, db_session, user):
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.get("/tutorial/status")
        assert response.status_code == 200
        assert response.json()["step"] == 0

        response = client.post("/tutorial/advance", json={"step": 1})
        assert response.status_code == 200
        assert response.json()["step"] == 0

        response = client.post("/tutorial/advance", json={"step": 999})
        assert response.status_code == 200
        assert response.json()["step"] == 0

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

        response = client.post("/tutorial/advance", json={"step": 0})
        assert response.status_code == 200
        assert response.json()["step"] == 1
        response = client.post("/tutorial/advance", json={"step": 7})
        assert response.status_code == 200
        assert response.json()["step"] == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def _battle_report_content(*, initial: int, losses: int, loot: int = 0) -> str:
    return json.dumps(
        {
            "attacker": {
                "initial": {"basic_infantry": initial},
                "losses": {"basic_infantry": losses},
            },
            "defender": {"initial": {}, "losses": {}},
            "loot": {"wood": loot, "clay": 0, "iron": 0},
        }
    )


def test_battle_return_requirement_matches_resolver_contract():
    wiped = models.Report(
        world_id=1,
        report_type="battle",
        content=_battle_report_content(initial=1, losses=1),
    )
    survivor = models.Report(
        world_id=1,
        report_type="battle",
        content=_battle_report_content(initial=2, losses=1),
    )
    loot_only = models.Report(
        world_id=1,
        report_type="battle",
        content=_battle_report_content(initial=1, losses=1, loot=10),
    )
    malformed = models.Report(world_id=1, report_type="battle", content="not-json")

    assert tutorial._battle_requires_return(wiped) is False
    assert tutorial._battle_requires_return(survivor) is True
    assert tutorial._battle_requires_return(loot_only) is True
    assert tutorial._battle_requires_return(malformed) is True


def test_total_defeat_without_loot_completes_tutorial_without_phantom_return(
    db_session, user
):
    world = db_session.query(models.World).first()
    user.world_id = world.id
    city = models.City(
        name="Recovery Capital",
        owner_id=user.id,
        world_id=world.id,
        x=31,
        y=31,
    )
    barbarian = models.City(
        name="Recovery Barbarian",
        owner_id=None,
        world_id=world.id,
        x=32,
        y=31,
    )
    db_session.add_all([user, city, barbarian])
    db_session.flush()
    db_session.add(models.Building(city_id=city.id, name="barracks", level=1))
    db_session.add(
        models.Movement(
            origin_city_id=city.id,
            target_city_id=barbarian.id,
            world_id=world.id,
            movement_type="attack",
            troops={"basic_infantry": 1},
            resources={},
            arrival_time=utc_now() - timedelta(seconds=1),
            status="completed",
        )
    )
    db_session.add(
        models.Report(
            city_id=city.id,
            world_id=world.id,
            report_type="battle",
            content=_battle_report_content(initial=1, losses=1),
            attacker_city_id=city.id,
            defender_city_id=barbarian.id,
        )
    )
    db_session.commit()

    progress = tutorial.get_progress(db_session, user)
    assert progress["step"] == tutorial.FINAL_STEP
    assert progress["completed"] is True
    assert (
        db_session.query(models.Movement)
        .filter(
            models.Movement.target_city_id == city.id,
            models.Movement.movement_type == "return",
        )
        .count()
        == 0
    )

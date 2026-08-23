from datetime import timedelta
from typing import Any, cast

from sqlalchemy.orm import Session

from app import models
from app.services import balance, movement, production, world_gen
from app.utils import utc_now


def test_oasis_generation(db_session: Session):
    # Create a world using the service
    world = world_gen.create_world(db_session, name="Oasis World", speed=1.0)

    # Check if oases were created
    oases = db_session.query(models.Oasis).filter(models.Oasis.world_id == world.id).all()
    assert len(oases) > 0

    # Check properties
    oasis = oases[0]
    assert oasis.resource_type in balance.RESOURCE_FIELDS
    assert oasis.bonus_percent in [25, 50]
    assert isinstance(oasis.troops, dict)


def test_oasis_combat_and_conquest(db_session: Session, user: models.User, city: models.City):
    # Setup
    world = city.world

    # Create an Oasis near the city
    oasis = models.Oasis(
        world_id=world.id,
        x=city.x + 1,
        y=city.y + 1,
        resource_type="wood",
        bonus_percent=25,
        troops={"rat": 5},  # Weak defense
    )
    db_session.add(oasis)
    db_session.commit()

    # Add troops to city
    t = models.Troop(city_id=city.id, unit_type="heavy_cavalry", quantity=100)
    db_session.add(t)

    # Add Hero to user and set status to moving (simulated)
    hero = models.Hero(
        user_id=user.id,
        name="Conqueror",
        attack_points=10,
        defense_points=0,
        status="home",
    )
    db_session.add(hero)
    db_session.commit()

    # Create an already-arrived movement with Hero participation simulated.
    move = models.Movement(
        origin_city_id=city.id,
        target_oasis_id=oasis.id,
        world_id=world.id,
        movement_type="attack",
        troops={"heavy_cavalry": 100},
        arrival_time=utc_now() - timedelta(seconds=1),
        status="ongoing",
    )
    db_session.add(move)
    db_session.commit()

    hero.status = "moving"
    db_session.commit()

    movement.resolve_due_movements(db_session)

    db_session.refresh(oasis)
    db_session.refresh(hero)

    assert cast(int, oasis.owner_city_id) == city.id
    assert cast(dict[str, Any], oasis.troops) == {}
    assert hero.health > 0

    report = db_session.query(models.Report).filter(models.Report.city_id == city.id).first()
    assert report is not None
    content_str = str(report.content)
    assert "Oasis Conquistado" in content_str or str(report.report_type) == "battle"


def test_oasis_production_bonus(db_session: Session, city: models.City):
    world = city.world

    oasis = models.Oasis(
        world_id=world.id,
        x=city.x + 1,
        y=city.y + 1,
        resource_type="wood",
        bonus_percent=25,
        owner_city_id=city.id,
    )
    db_session.add(oasis)
    db_session.commit()
    db_session.refresh(city)

    prod = production.get_production_per_hour(db_session, city)

    assert prod["wood"] == balance.PRODUCTION_RATES_PER_HOUR["wood"] * 1.25
    for resource in ("stone", "iron", "gold"):
        assert prod[resource] == balance.PRODUCTION_RATES_PER_HOUR[resource]

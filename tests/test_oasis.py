from datetime import timedelta
from typing import Any, cast

from sqlalchemy.orm import Session

from app import models
from app.services import balance, movement, production, pve, world_gen
from app.utils import utc_now


def test_oasis_generation(db_session: Session):
    world = world_gen.create_world(db_session, name="Oasis World", speed=1.0)

    oases = (
        db_session.query(models.Oasis)
        .filter(models.Oasis.world_id == world.id)
        .order_by(models.Oasis.id.asc())
        .all()
    )
    assert len(oases) == pve.PVE_OASIS_TARGET_TOTAL

    for oasis in oases:
        tier = pve.oasis_tier(oasis)
        profile = pve.OASIS_PROFILES[tier]
        assert oasis.resource_type in balance.RESOURCE_FIELDS
        assert oasis.bonus_percent == profile["bonus_percent"]
        assert isinstance(oasis.troops, dict)
        assert oasis.troops == profile["guards"]
        assert set(oasis.troops).issubset(balance.UNIT_COMBAT_STATS)


def test_oasis_combat_and_conquest(db_session: Session, user: models.User, city: models.City):
    world = city.world

    oasis = models.Oasis(
        world_id=world.id,
        x=city.x + 1,
        y=city.y + 1,
        resource_type="wood",
        bonus_percent=25,
        troops={"basic_infantry": 1},
    )
    db_session.add(oasis)
    db_session.commit()

    t = models.Troop(city_id=city.id, unit_type="heavy_cavalry", quantity=100)
    db_session.add(t)

    hero = models.Hero(
        user_id=user.id,
        name="Conqueror",
        attack_points=10,
        defense_points=0,
        status="home",
    )
    db_session.add(hero)
    db_session.commit()

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
    assert str(report.report_type) == "battle"


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

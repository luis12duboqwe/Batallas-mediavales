from datetime import timedelta
import json
from typing import Any, cast

from sqlalchemy.orm import Session

from app import models
from app.services import balance, movement, production, pve_rules, world_gen
from app.utils import utc_now


def test_oasis_generation_uses_versioned_profiles_and_land_tiles(db_session: Session):
    world = world_gen.create_world(db_session, name="Oasis World", speed=1.0)
    expected_barbarians, expected_oases = pve_rules.world_content_counts(world.map_size)

    barbarians = (
        db_session.query(models.City)
        .filter(models.City.world_id == world.id, models.City.owner_id.is_(None))
        .all()
    )
    oases = db_session.query(models.Oasis).filter(models.Oasis.world_id == world.id).all()
    assert len(barbarians) == expected_barbarians
    assert len(oases) == expected_oases
    assert world.pve_rules_version == pve_rules.PVE_RULES_VERSION

    for oasis in oases:
        difficulty, profile = pve_rules.oasis_profile(
            world_id=world.id,
            x=oasis.x,
            y=oasis.y,
            rules_version=world.pve_rules_version,
        )
        assert difficulty in pve_rules.DIFFICULTY_ORDER
        assert world_gen.get_tile_type(oasis.x, oasis.y) != "water"
        assert oasis.resource_type in balance.RESOURCE_FIELDS
        assert oasis.bonus_percent == profile["bonus_percent"]
        assert oasis.troops == profile["guard_target"]
        assert set(oasis.troops).issubset(balance.UNIT_COMBAT_STATS)


def _canonical_oasis(db_session: Session, city: models.City) -> models.Oasis:
    oasis = models.Oasis(
        world_id=city.world_id,
        x=city.x + 1,
        y=city.y + 1,
        resource_type="wood",
        bonus_percent=25,
        troops={"basic_infantry": 1},
    )
    db_session.add(oasis)
    db_session.commit()
    db_session.refresh(oasis)
    return oasis


def _due_oasis_attack(db_session: Session, city: models.City, oasis: models.Oasis) -> models.Movement:
    movement_row = models.Movement(
        origin_city_id=city.id,
        target_oasis_id=oasis.id,
        world_id=city.world_id,
        movement_type="attack",
        troops={"heavy_cavalry": 100},
        arrival_time=utc_now() - timedelta(seconds=1),
        speed_used=balance.UNIT_SPEED["heavy_cavalry"],
        status="ongoing",
    )
    db_session.add(movement_row)
    db_session.commit()
    return movement_row


def test_oasis_victory_without_hero_does_not_capture(db_session: Session, city: models.City):
    oasis = _canonical_oasis(db_session, city)
    _due_oasis_attack(db_session, city, oasis)

    movement.resolve_due_movements(db_session)
    db_session.refresh(oasis)

    assert oasis.owner_city_id is None
    assert cast(dict[str, Any], oasis.troops) == {}
    report = (
        db_session.query(models.Report)
        .filter_by(city_id=city.id, report_type="battle")
        .order_by(models.Report.id.desc())
        .first()
    )
    assert report is not None
    payload = json.loads(str(report.content))
    assert payload["conquest"] is False
    assert payload["pve"]["capture_requires_living_hero"] is True
    assert payload["pve"]["rules_version"] == pve_rules.PVE_RULES_VERSION


def test_oasis_combat_and_conquest_with_living_hero_is_auditable(
    db_session: Session,
    user: models.User,
    city: models.City,
):
    world = city.world
    world.pve_rules_version = pve_rules.PVE_RULES_VERSION
    db_session.add(world)
    oasis = _canonical_oasis(db_session, city)

    hero = models.Hero(
        user_id=user.id,
        name="Conqueror",
        attack_points=10,
        defense_points=0,
        status="moving",
    )
    db_session.add(hero)
    db_session.commit()
    _due_oasis_attack(db_session, city, oasis)

    movement.resolve_due_movements(db_session)

    db_session.refresh(oasis)
    db_session.refresh(hero)
    assert cast(int, oasis.owner_city_id) == city.id
    assert cast(dict[str, Any], oasis.troops) == {}
    assert hero.health > 0

    report = (
        db_session.query(models.Report)
        .filter_by(city_id=city.id, report_type="battle")
        .order_by(models.Report.id.desc())
        .first()
    )
    assert report is not None
    payload = json.loads(str(report.content))
    assert payload["type"] == "oasis_battle"
    assert payload["conquest"] is True
    assert payload["pve"]["rules_version"] == pve_rules.PVE_RULES_VERSION
    assert payload["pve"]["difficulty"] in pve_rules.DIFFICULTY_ORDER
    assert payload["pve"]["resource_type"] == "wood"
    assert payload["pve"]["bonus_percent"] == 25
    assert payload["pve"]["capture_requires_living_hero"] is True
    assert payload["combat"]["seed"]


def test_oasis_production_bonus_is_the_persistent_reward(db_session: Session, city: models.City):
    oasis = models.Oasis(
        world_id=city.world_id,
        x=city.x + 1,
        y=city.y + 1,
        resource_type="wood",
        bonus_percent=25,
        owner_city_id=city.id,
        troops={},
    )
    db_session.add(oasis)
    db_session.commit()
    db_session.refresh(city)

    prod = production.get_production_per_hour(db_session, city)

    assert prod["wood"] == balance.PRODUCTION_RATES_PER_HOUR["wood"] * 1.25
    for resource in ("stone", "iron", "gold"):
        assert prod[resource] == balance.PRODUCTION_RATES_PER_HOUR[resource]

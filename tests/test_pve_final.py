import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.seed import CANONICAL_BARBARIANS, DEFAULT_WORLD_NAME, seed_game
from app.services import balance, pve
from app.utils import utc_now


EXPECTED_CANONICAL_TIERS = (1, 1, 1, 2, 2, 2, 3, 3)


def _seeded_world(db_session) -> models.World:
    seed_game(db_session)
    return (
        db_session.query(models.World)
        .filter(models.World.name == DEFAULT_WORLD_NAME)
        .one()
    )


def test_fresh_world_uses_versioned_tiered_pve_catalog(db_session):
    world = _seeded_world(db_session)

    manifest = json.loads(world.special_rules)
    assert manifest["pve"]["version"] == pve.PVE_RULES_VERSION

    barbarians = (
        db_session.query(models.City)
        .filter(
            models.City.world_id == world.id,
            models.City.owner_id.is_(None),
        )
        .order_by(models.City.id.asc())
        .all()
    )
    assert len(barbarians) == pve.PVE_BARBARIAN_TARGET_ACTIVE == len(CANONICAL_BARBARIANS)

    by_coord = {(city.x, city.y): city for city in barbarians}
    for index, coord in enumerate(CANONICAL_BARBARIANS):
        city = by_coord[coord]
        expected_tier = EXPECTED_CANONICAL_TIERS[index]
        profile = pve.BARBARIAN_PROFILES[expected_tier]

        assert pve.barbarian_tier(city) == expected_tier
        assert f"T{expected_tier}" in city.name
        assert {
            resource: float(getattr(city, resource))
            for resource in balance.RESOURCE_FIELDS
        } == pytest.approx(profile["resources"])
        assert {building.name: building.level for building in city.buildings} == profile["buildings"]
        assert {troop.unit_type: troop.quantity for troop in city.troops} == profile["troops"]

    oases = (
        db_session.query(models.Oasis)
        .filter(models.Oasis.world_id == world.id)
        .order_by(models.Oasis.id.asc())
        .all()
    )
    assert len(oases) == pve.PVE_OASIS_TARGET_TOTAL
    assert {pve.oasis_tier(oasis) for oasis in oases} == {1, 2, 3}

    for oasis in oases:
        tier = pve.oasis_tier(oasis)
        profile = pve.OASIS_PROFILES[tier]
        assert oasis.resource_type in balance.RESOURCE_FIELDS
        assert oasis.bonus_percent == profile["bonus_percent"]
        assert oasis.troops == profile["guards"]
        assert set(oasis.troops).issubset(balance.UNIT_COMBAT_STATS)
        assert "rat" not in oasis.troops
        assert "spider" not in oasis.troops


def test_world_pve_reconciliation_is_idempotent_and_preserves_progress(db_session):
    world = _seeded_world(db_session)
    city = (
        db_session.query(models.City)
        .filter(
            models.City.world_id == world.id,
            models.City.x == CANONICAL_BARBARIANS[0][0],
            models.City.y == CANONICAL_BARBARIANS[0][1],
        )
        .one()
    )
    city.wood = 123.0
    city.troops[0].quantity = 3
    db_session.commit()

    first = pve.ensure_world_pve(
        db_session,
        world,
        canonical_barbarian_coords=CANONICAL_BARBARIANS,
    )
    second = pve.ensure_world_pve(
        db_session,
        world,
        canonical_barbarian_coords=CANONICAL_BARBARIANS,
    )
    db_session.commit()

    assert first == {"barbarians_created": 0, "oases_created": 0}
    assert second == {"barbarians_created": 0, "oases_created": 0}
    db_session.refresh(city)
    assert city.wood == 123.0
    assert city.troops[0].quantity == 3


def test_conquered_barbarian_is_preserved_and_replaced_on_fresh_coordinate(
    db_session,
    user,
):
    world = _seeded_world(db_session)
    conquered = (
        db_session.query(models.City)
        .filter(
            models.City.world_id == world.id,
            models.City.x == CANONICAL_BARBARIANS[0][0],
            models.City.y == CANONICAL_BARBARIANS[0][1],
        )
        .one()
    )
    conquered.owner_id = user.id
    conquered.wood = 77.0
    conquered_id = conquered.id
    db_session.commit()

    result = pve.ensure_world_pve(
        db_session,
        world,
        canonical_barbarian_coords=CANONICAL_BARBARIANS,
    )
    db_session.commit()

    assert result["barbarians_created"] == 1
    db_session.expire_all()
    conquered = db_session.query(models.City).filter(models.City.id == conquered_id).one()
    assert conquered.owner_id == user.id
    assert conquered.wood == 77.0

    active = (
        db_session.query(models.City)
        .filter(
            models.City.world_id == world.id,
            models.City.owner_id.is_(None),
        )
        .all()
    )
    assert len(active) == pve.PVE_BARBARIAN_TARGET_ACTIVE
    assert all(city.id != conquered_id for city in active)
    assert any((city.x, city.y) not in CANONICAL_BARBARIANS for city in active)


def test_pve_tick_is_bucket_idempotent_and_regenerates_unowned_oasis(db_session):
    world = _seeded_world(db_session)
    oasis = (
        db_session.query(models.Oasis)
        .filter(models.Oasis.world_id == world.id, models.Oasis.owner_city_id.is_(None))
        .order_by(models.Oasis.id.asc())
        .first()
    )
    assert oasis is not None
    tier = pve.oasis_tier(oasis)
    profile = pve.OASIS_PROFILES[tier]
    oasis.troops = {}
    db_session.commit()

    tick_at = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    first = pve.process_pve_tick(db_session, now=tick_at)
    db_session.commit()
    db_session.refresh(oasis)

    expected_first = {
        unit: max(1, int(math.ceil(amount * profile["regeneration_fraction"])))
        for unit, amount in profile["guards"].items()
    }
    assert first["worlds_processed"] >= 1
    assert oasis.troops == expected_first

    snapshot = dict(oasis.troops)
    second = pve.process_pve_tick(db_session, now=tick_at + timedelta(seconds=30))
    db_session.commit()
    db_session.refresh(oasis)
    assert second["worlds_processed"] == 0
    assert oasis.troops == snapshot

    third = pve.process_pve_tick(db_session, now=tick_at + timedelta(minutes=5))
    db_session.commit()
    db_session.refresh(oasis)
    assert third["worlds_processed"] >= 1
    for unit, target in profile["guards"].items():
        assert snapshot.get(unit, 0) <= oasis.troops.get(unit, 0) <= target


def test_conquered_oasis_does_not_regenerate(db_session, user):
    world = _seeded_world(db_session)
    owner_city = models.City(
        name="Oasis Owner",
        owner_id=user.id,
        world_id=world.id,
        x=1,
        y=1,
        wood=100,
        stone=100,
        iron=100,
        gold=100,
        last_production=utc_now(),
    )
    db_session.add(owner_city)
    db_session.flush()
    oasis = (
        db_session.query(models.Oasis)
        .filter(models.Oasis.world_id == world.id)
        .order_by(models.Oasis.id.asc())
        .first()
    )
    assert oasis is not None
    oasis.owner_city_id = owner_city.id
    oasis.troops = {}
    db_session.commit()

    pve.process_pve_tick(
        db_session,
        now=datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    db_session.refresh(oasis)
    assert oasis.owner_city_id == owner_city.id
    assert oasis.troops == {}


def test_pve_refuses_silent_rule_version_change(db_session):
    world = _seeded_world(db_session)
    rules = json.loads(world.special_rules)
    rules["pve"]["version"] = "future-incompatible-version"
    world.special_rules = json.dumps(rules)
    db_session.commit()

    with pytest.raises(RuntimeError, match="Unsupported PvE rules version"):
        pve.ensure_world_pve(db_session, world)

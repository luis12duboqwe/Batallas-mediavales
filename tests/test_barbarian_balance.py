from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.services import balance, barbarian_ai, production, pve_rules


def _create_barbarian(db_session, *, x: int = 61, y: int = 62):
    world = db_session.query(models.World).first()
    world.pve_rules_version = pve_rules.PVE_RULES_VERSION
    world.pve_last_tick_at = None
    city = models.City(
        name="PvE Final",
        owner_id=None,
        world_id=world.id,
        x=x,
        y=y,
        wood=2000.0,
        stone=2000.0,
        iron=2000.0,
        gold=2000.0,
    )
    db_session.add_all([world, city])
    db_session.commit()
    db_session.refresh(city)
    return world, city


def test_barbarian_tick_is_deterministic_bounded_and_idempotent(db_session):
    world, city = _create_barbarian(db_session)
    difficulty, profile = pve_rules.barbarian_profile(
        world_id=world.id,
        x=city.x,
        y=city.y,
        rules_version=world.pve_rules_version,
    )
    assert difficulty in pve_rules.DIFFICULTY_ORDER

    before = {resource: float(getattr(city, resource)) for resource in balance.RESOURCE_FIELDS}
    first_unit = next(iter(profile["troop_caps"]))
    recruit_cost = balance.UNIT_CATALOG[first_unit]["training_cost"]
    now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

    result = barbarian_ai.process_barbarian_growth(db_session, now=now)
    db_session.commit()
    db_session.expire_all()
    persisted = db_session.query(models.City).filter_by(id=city.id).one()

    assert result["worlds"] == 1
    assert result["barbarians"] >= 1
    assert result["recruited"] >= 1
    for resource in balance.RESOURCE_FIELDS:
        expected_before_cost = min(
            before[resource] + profile["resource_regen_per_tick"],
            production.get_storage_limit(persisted),
        )
        expected = expected_before_cost - recruit_cost.get(resource, 0.0)
        assert getattr(persisted, resource) == pytest.approx(expected)

    troop = (
        db_session.query(models.Troop)
        .filter_by(city_id=city.id, unit_type=first_unit)
        .one()
    )
    assert troop.quantity == min(profile["recruits_per_tick"], profile["troop_caps"][first_unit])

    snapshot = (
        {resource: getattr(persisted, resource) for resource in balance.RESOURCE_FIELDS},
        troop.quantity,
    )
    retry = barbarian_ai.process_barbarian_growth(db_session, now=now + timedelta(seconds=30))
    db_session.commit()
    db_session.expire_all()
    persisted = db_session.query(models.City).filter_by(id=city.id).one()
    troop = db_session.query(models.Troop).filter_by(city_id=city.id, unit_type=first_unit).one()
    assert retry["worlds"] == 0
    assert snapshot == (
        {resource: getattr(persisted, resource) for resource in balance.RESOURCE_FIELDS},
        troop.quantity,
    )


def test_barbarian_tick_never_exceeds_profile_troop_caps(db_session):
    world, city = _create_barbarian(db_session, x=63, y=64)
    _, profile = pve_rules.barbarian_profile(
        world_id=world.id,
        x=city.x,
        y=city.y,
        rules_version=world.pve_rules_version,
    )
    for unit_type, cap in profile["troop_caps"].items():
        db_session.add(models.Troop(city_id=city.id, unit_type=unit_type, quantity=cap))
    db_session.commit()

    result = barbarian_ai.process_barbarian_growth(
        db_session,
        now=datetime(2026, 8, 25, 13, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    assert result["recruited"] == 0
    for unit_type, cap in profile["troop_caps"].items():
        troop = db_session.query(models.Troop).filter_by(city_id=city.id, unit_type=unit_type).one()
        assert troop.quantity == cap


def test_neutral_oasis_regenerates_canonical_guards_and_drops_legacy_aliases(db_session):
    world = db_session.query(models.World).first()
    world.pve_rules_version = pve_rules.PVE_RULES_VERSION
    world.pve_last_tick_at = None
    oasis = models.Oasis(
        world_id=world.id,
        x=65,
        y=66,
        resource_type="wood",
        bonus_percent=25,
        owner_city_id=None,
        troops={"rat": 99, "spider": 99},
    )
    db_session.add_all([world, oasis])
    db_session.commit()

    _, profile = pve_rules.oasis_profile(
        world_id=world.id,
        x=oasis.x,
        y=oasis.y,
        rules_version=world.pve_rules_version,
    )
    result = barbarian_ai.process_barbarian_growth(
        db_session,
        now=datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    db_session.refresh(oasis)

    assert result["oases"] >= 1
    assert result["guards"] > 0
    assert "rat" not in oasis.troops
    assert "spider" not in oasis.troops
    assert set(oasis.troops).issubset(profile["guard_target"])
    assert set(oasis.troops).issubset(balance.UNIT_COMBAT_STATS)
    for unit_type, amount in oasis.troops.items():
        assert 0 < amount <= profile["guard_target"][unit_type]


def test_player_owned_oasis_does_not_regenerate_neutral_guards(db_session, city):
    world = city.world
    world.pve_rules_version = pve_rules.PVE_RULES_VERSION
    world.pve_last_tick_at = None
    oasis = models.Oasis(
        world_id=world.id,
        x=67,
        y=68,
        resource_type="gold",
        bonus_percent=50,
        owner_city_id=city.id,
        troops={},
    )
    db_session.add_all([world, oasis])
    db_session.commit()

    barbarian_ai.process_barbarian_growth(
        db_session,
        now=datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    db_session.refresh(oasis)
    assert oasis.troops == {}


def test_world_with_unrecognized_pve_version_is_not_silently_rebalanced(db_session):
    world, city = _create_barbarian(db_session, x=69, y=70)
    world.pve_rules_version = "future-or-legacy-pve-version"
    world.pve_last_tick_at = None
    before = {resource: getattr(city, resource) for resource in balance.RESOURCE_FIELDS}
    db_session.commit()

    result = barbarian_ai.process_barbarian_growth(
        db_session,
        now=datetime(2026, 8, 25, 16, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    db_session.refresh(city)

    assert result["worlds"] == 0
    assert before == {resource: getattr(city, resource) for resource in balance.RESOURCE_FIELDS}

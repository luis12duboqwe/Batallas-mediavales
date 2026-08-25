import pytest

from app import models
from app.seed import (
    BARBARIAN_BUILDINGS,
    BARBARIAN_TROOPS,
    CANONICAL_BARBARIANS,
    DEFAULT_WORLD_NAME,
    seed_game,
)
from app.services import balance, pve


def test_seed_exports_canonical_pve_aliases():
    assert BARBARIAN_BUILDINGS is balance.BARBARIAN_STARTING_BUILDINGS
    assert BARBARIAN_TROOPS is balance.BARBARIAN_STARTING_TROOPS


def test_canonical_seed_is_idempotent(db_session):
    first = seed_game(db_session)
    second = seed_game(db_session)

    worlds = (
        db_session.query(models.World)
        .filter(models.World.name == DEFAULT_WORLD_NAME)
        .all()
    )
    assert len(worlds) == 1
    world = worlds[0]

    barbarians = (
        db_session.query(models.City)
        .filter(
            models.City.world_id == world.id,
            models.City.owner_id.is_(None),
        )
        .all()
    )
    oases = db_session.query(models.Oasis).filter(models.Oasis.world_id == world.id).all()

    assert first.world_created is True
    assert first.barbarians_created == len(CANONICAL_BARBARIANS)
    assert second.world_created is False
    assert second.barbarians_created == 0
    assert len(barbarians) == pve.PVE_BARBARIAN_TARGET_ACTIVE
    assert len(oases) == pve.PVE_OASIS_TARGET_TOTAL

    for city in barbarians:
        tier = pve.barbarian_tier(city)
        assert tier in pve.PVE_TIERS
        profile = pve.BARBARIAN_PROFILES[tier]
        assert {building.name: building.level for building in city.buildings} == profile["buildings"]
        assert {troop.unit_type: troop.quantity for troop in city.troops} == profile["troops"]
        assert {
            resource: float(getattr(city, resource))
            for resource in balance.RESOURCE_FIELDS
        } == pytest.approx(profile["resources"])
        assert city.population_max == balance.BARBARIAN_POPULATION_MAX


def test_seed_does_not_reset_existing_barbarian_progress(db_session):
    result = seed_game(db_session)
    x, y = CANONICAL_BARBARIANS[0]
    city = (
        db_session.query(models.City)
        .filter(
            models.City.world_id == result.world_id,
            models.City.x == x,
            models.City.y == y,
        )
        .one()
    )

    basic_infantry = next(
        troop for troop in city.troops if troop.unit_type == "basic_infantry"
    )
    town_hall = next(
        building for building in city.buildings if building.name == "town_hall"
    )

    city.wood = 123.0
    basic_infantry.quantity = 3
    town_hall.level = 2
    db_session.commit()

    second = seed_game(db_session)
    assert second.barbarians_created == 0

    db_session.expire_all()
    city = (
        db_session.query(models.City)
        .filter(
            models.City.world_id == result.world_id,
            models.City.x == x,
            models.City.y == y,
        )
        .one()
    )
    basic_infantry = next(
        troop for troop in city.troops if troop.unit_type == "basic_infantry"
    )
    town_hall = next(
        building for building in city.buildings if building.name == "town_hall"
    )

    assert city.wood == 123.0
    assert basic_infantry.quantity == 3
    assert town_hall.level == 2


def test_seed_refuses_to_overwrite_player_city(db_session, user):
    world = models.World(
        name=DEFAULT_WORLD_NAME,
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=100,
        is_active=True,
    )
    db_session.add(world)
    db_session.flush()

    x, y = CANONICAL_BARBARIANS[0]
    db_session.add(
        models.City(
            name="Player Capital",
            owner_id=user.id,
            world_id=world.id,
            x=x,
            y=y,
        )
    )
    db_session.commit()

    with pytest.raises(RuntimeError, match="occupied by a player city"):
        seed_game(db_session)

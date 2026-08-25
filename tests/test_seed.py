from app import models
from app.seed import DEFAULT_WORLD_NAME, seed_game
from app.services import balance, pve_rules, world_gen


def test_canonical_seed_is_idempotent_and_uses_final_pve_rules(db_session):
    first = seed_game(db_session)
    second = seed_game(db_session)

    worlds = (
        db_session.query(models.World)
        .filter(models.World.name == DEFAULT_WORLD_NAME)
        .all()
    )
    assert len(worlds) == 1
    world = worlds[0]
    expected_barbarians, expected_oases = pve_rules.world_content_counts(world.map_size)

    assert first.world_created is True
    assert first.barbarians_created == expected_barbarians
    assert first.oases_created == expected_oases
    assert second.world_created is False
    assert second.barbarians_created == 0
    assert second.oases_created == 0
    assert world.pve_rules_version == pve_rules.PVE_RULES_VERSION

    barbarians = (
        db_session.query(models.City)
        .filter(models.City.world_id == world.id, models.City.owner_id.is_(None))
        .all()
    )
    oases = db_session.query(models.Oasis).filter_by(world_id=world.id).all()
    assert len(barbarians) == expected_barbarians
    assert len(oases) == expected_oases

    coordinates = {(city.x, city.y) for city in barbarians}
    coordinates.update((oasis.x, oasis.y) for oasis in oases)
    assert len(coordinates) == expected_barbarians + expected_oases
    assert all(world_gen.get_tile_type(x, y) != "water" for x, y in coordinates)


def test_seeded_barbarians_match_coordinate_difficulty_profiles(db_session):
    result = seed_game(db_session)
    world = db_session.query(models.World).filter_by(id=result.world_id).one()
    barbarians = (
        db_session.query(models.City)
        .filter(models.City.world_id == world.id, models.City.owner_id.is_(None))
        .all()
    )

    observed_difficulties = set()
    for city in barbarians:
        difficulty, profile = pve_rules.barbarian_profile(
            world_id=world.id,
            x=city.x,
            y=city.y,
            rules_version=world.pve_rules_version,
        )
        observed_difficulties.add(difficulty)
        assert difficulty in city.name
        assert {resource: getattr(city, resource) for resource in balance.RESOURCE_FIELDS} == profile["starting_resources"]
        assert {building.name: building.level for building in city.buildings} == dict(profile["buildings"])
        assert {troop.unit_type: troop.quantity for troop in city.troops} == dict(profile["starting_troops"])
        assert city.population_max == profile["population_max"]

    assert observed_difficulties.issubset(set(pve_rules.DIFFICULTY_ORDER))
    assert len(observed_difficulties) >= 2


def test_seeded_oases_use_canonical_guards_and_profile_rewards(db_session):
    result = seed_game(db_session)
    world = db_session.query(models.World).filter_by(id=result.world_id).one()
    oases = db_session.query(models.Oasis).filter_by(world_id=world.id).all()

    assert oases
    for oasis in oases:
        difficulty, profile = pve_rules.oasis_profile(
            world_id=world.id,
            x=oasis.x,
            y=oasis.y,
            rules_version=world.pve_rules_version,
        )
        assert difficulty in pve_rules.DIFFICULTY_ORDER
        assert oasis.resource_type in balance.RESOURCE_FIELDS
        assert oasis.bonus_percent == profile["bonus_percent"]
        assert oasis.troops == profile["guard_target"]
        assert set(oasis.troops).issubset(balance.UNIT_COMBAT_STATS)


def test_seed_does_not_reset_existing_pve_progress(db_session):
    result = seed_game(db_session)
    city = (
        db_session.query(models.City)
        .filter(models.City.world_id == result.world_id, models.City.owner_id.is_(None))
        .order_by(models.City.id.asc())
        .first()
    )
    assert city is not None
    troop = city.troops[0]
    building = city.buildings[0]

    city.wood = 123.0
    troop.quantity = 3
    building.level = max(1, building.level + 1)
    changed_level = building.level
    db_session.commit()

    second = seed_game(db_session)
    assert second.barbarians_created == 0
    assert second.oases_created == 0

    db_session.expire_all()
    persisted = db_session.query(models.City).filter_by(id=city.id).one()
    persisted_troop = db_session.query(models.Troop).filter_by(id=troop.id).one()
    persisted_building = db_session.query(models.Building).filter_by(id=building.id).one()
    assert persisted.wood == 123.0
    assert persisted_troop.quantity == 3
    assert persisted_building.level == changed_level


def test_seed_leaves_preexisting_world_and_player_city_untouched(db_session, user):
    world = models.World(
        name=DEFAULT_WORLD_NAME,
        speed_modifier=1.0,
        resource_modifier=1.0,
        map_size=100,
        is_active=True,
        pve_rules_version=pve_rules.PVE_RULES_VERSION,
    )
    db_session.add(world)
    db_session.flush()
    player_city = models.City(
        name="Player Capital",
        owner_id=user.id,
        world_id=world.id,
        x=10,
        y=10,
    )
    db_session.add(player_city)
    db_session.commit()

    result = seed_game(db_session)
    assert result.world_created is False
    assert result.barbarians_created == 0
    assert result.oases_created == 0
    assert db_session.query(models.City).filter_by(id=player_city.id).one().owner_id == user.id

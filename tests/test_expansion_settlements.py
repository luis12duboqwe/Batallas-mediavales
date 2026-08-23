from datetime import timedelta

import pytest

from app import models
from app.services import balance, building, expansion, production, world_gen
from app.utils import utc_now


def _membership(db_session, user, city, points=0):
    membership = models.PlayerWorld(
        user_id=user.id,
        world_id=city.world_id,
        starting_city_id=city.id,
        expansion_points=points,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def _set_resources(city, amount):
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, float(amount))
    city.last_production = utc_now()


def test_church_and_cathedral_completion_mint_points_exactly_once(
    db_session,
    user,
    city,
):
    membership = _membership(db_session, user, city)
    church = models.Building(city_id=city.id, name="church", level=0)
    cathedral = models.Building(city_id=city.id, name="cathedral", level=0)
    db_session.add_all([church, cathedral])
    db_session.flush()
    db_session.add_all(
        [
            models.BuildingQueue(
                city_id=city.id,
                building_type="church",
                target_level=1,
                finish_time=utc_now() - timedelta(seconds=1),
                paid_cost={},
            ),
            models.BuildingQueue(
                city_id=city.id,
                building_type="cathedral",
                target_level=1,
                finish_time=utc_now() - timedelta(seconds=1),
                paid_cost={},
            ),
        ]
    )
    db_session.commit()

    finished = building.process_building_queues(db_session)
    assert len(finished) == 2
    db_session.refresh(membership)
    assert membership.expansion_points == 4

    # Completed queues are deleted, so another worker pass cannot mint twice.
    assert building.process_building_queues(db_session) == []
    db_session.refresh(membership)
    assert membership.expansion_points == 4

    # Even a stale/duplicate queue for an already completed target level is harmless.
    db_session.add(
        models.BuildingQueue(
            city_id=city.id,
            building_type="church",
            target_level=1,
            finish_time=utc_now() - timedelta(seconds=1),
            paid_cost={},
        )
    )
    db_session.commit()
    building.process_building_queues(db_session)
    db_session.refresh(membership)
    assert membership.expansion_points == 4


def test_point_generator_without_membership_rolls_back_completion(
    db_session,
    city,
):
    church = models.Building(city_id=city.id, name="church", level=0)
    queue = models.BuildingQueue(
        city_id=city.id,
        building_type="church",
        target_level=1,
        finish_time=utc_now() - timedelta(seconds=1),
        paid_cost={},
    )
    db_session.add_all([church, queue])
    db_session.commit()
    queue_id = queue.id

    with pytest.raises(RuntimeError, match="PlayerWorld membership"):
        building.process_building_queues(db_session)
    db_session.rollback()
    db_session.expire_all()

    assert (
        db_session.query(models.Building)
        .filter_by(city_id=city.id, name="church")
        .one()
        .level
        == 0
    )
    assert db_session.query(models.BuildingQueue).filter_by(id=queue_id).one_or_none() is not None


def test_camp_founding_consumes_points_and_resources_without_minting_resources(
    db_session,
    user,
    city,
    monkeypatch,
):
    membership = _membership(
        db_session,
        user,
        city,
        points=balance.SETTLEMENT_EXPANSION_POINT_COSTS["camp"],
    )
    _set_resources(city, 1000)
    db_session.commit()
    monkeypatch.setattr(world_gen, "get_tile_type", lambda x, y: "grass")

    camp = expansion.found_settlement(
        db_session,
        user,
        city,
        "Campamento Norte",
        10,
        11,
        "camp",
    )

    db_session.refresh(membership)
    db_session.refresh(city)
    assert membership.expansion_points == 0
    assert camp.settlement_type == "camp"
    assert camp.population_max == balance.CAMP_POPULATION_MAX
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(camp, resource) == pytest.approx(
            balance.CAMP_STARTING_RESOURCES[resource]
        )
        assert getattr(city, resource) == pytest.approx(
            1000.0 - balance.CAMP_FOUNDING_COST.get(resource, 0.0),
            abs=0.1,
        )

    assert {row.name for row in camp.buildings} == {
        definition["name"] for definition in balance.CAMP_STARTER_BUILDINGS
    }
    rates = production.get_production_per_hour(db_session, camp)
    assert rates == pytest.approx(
        {
            resource: rate * balance.CAMP_PRODUCTION_MULTIPLIER
            for resource, rate in balance.PRODUCTION_RATES_PER_HOUR.items()
        }
    )


def test_camp_cannot_build_expansion_generators_or_world_wonder(db_session, user, city):
    _membership(db_session, user, city, points=10)
    camp = models.City(
        name="Restricted Camp",
        owner_id=user.id,
        world_id=city.world_id,
        x=20,
        y=20,
        settlement_type="camp",
    )
    db_session.add(camp)
    db_session.commit()

    for building_name in ("church", "cathedral", "world_wonder", "town_hall"):
        with pytest.raises(ValueError, match="not available in camps"):
            building.queue_upgrade(db_session, camp, building_name)

    available = {entry["name"] for entry in building.get_available_buildings(db_session, camp)}
    assert available == set(balance.CAMP_ALLOWED_BUILDINGS)


def test_promoting_camp_pays_exact_remaining_city_cost_and_points(
    db_session,
    user,
    city,
):
    membership = _membership(
        db_session,
        user,
        city,
        points=balance.CAMP_PROMOTION_POINT_COST,
    )
    camp = models.City(
        name="Camp to Promote",
        owner_id=user.id,
        world_id=city.world_id,
        x=21,
        y=21,
        settlement_type="camp",
        population_max=balance.CAMP_POPULATION_MAX,
        last_production=utc_now(),
    )
    _set_resources(camp, 1000)
    db_session.add(camp)
    db_session.flush()
    for definition in balance.CAMP_STARTER_BUILDINGS:
        db_session.add(
            models.Building(
                city_id=camp.id,
                name=definition["name"],
                level=definition["level"],
            )
        )
    db_session.commit()

    promoted = expansion.promote_camp(db_session, user, camp)

    db_session.refresh(membership)
    assert promoted.settlement_type == "city"
    assert promoted.population_max == balance.CITY_POPULATION_MAX
    assert membership.expansion_points == 0
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(promoted, resource) == pytest.approx(
            1000.0 - balance.CAMP_PROMOTION_COST.get(resource, 0.0),
            abs=0.1,
        )
    assert (
        db_session.query(models.Building)
        .filter_by(city_id=camp.id, name="town_hall")
        .one()
        .level
        == 1
    )

    for resource in balance.RESOURCE_FIELDS:
        assert balance.CAMP_FOUNDING_COST.get(resource, 0.0) + balance.CAMP_PROMOTION_COST.get(resource, 0.0) == pytest.approx(
            balance.CITY_FOUNDING_COST.get(resource, 0.0)
        )
    assert (
        balance.SETTLEMENT_EXPANSION_POINT_COSTS["camp"]
        + balance.CAMP_PROMOTION_POINT_COST
        == balance.SETTLEMENT_EXPANSION_POINT_COSTS["city"]
    )


def test_camp_cannot_be_promoted_after_world_closes(db_session, user, city):
    membership = _membership(
        db_session,
        user,
        city,
        points=balance.CAMP_PROMOTION_POINT_COST,
    )
    camp = models.City(
        name="Closed World Camp",
        owner_id=user.id,
        world_id=city.world_id,
        x=22,
        y=22,
        settlement_type="camp",
        population_max=balance.CAMP_POPULATION_MAX,
        last_production=utc_now(),
    )
    _set_resources(camp, 1000)
    city.world.is_active = False
    db_session.add_all([camp, city.world])
    db_session.commit()

    with pytest.raises(ValueError, match="World not found or inactive"):
        expansion.promote_camp(db_session, user, camp)

    db_session.expire_all()
    persisted_camp = db_session.query(models.City).filter_by(id=camp.id).one()
    persisted_membership = db_session.query(models.PlayerWorld).filter_by(id=membership.id).one()
    assert persisted_camp.settlement_type == "camp"
    assert persisted_membership.expansion_points == balance.CAMP_PROMOTION_POINT_COST
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(persisted_camp, resource) == pytest.approx(1000.0)


def test_direct_city_founding_requires_full_points_and_full_cost(
    db_session,
    user,
    city,
    monkeypatch,
):
    membership = _membership(
        db_session,
        user,
        city,
        points=balance.SETTLEMENT_EXPANSION_POINT_COSTS["city"],
    )
    _set_resources(city, 1000)
    db_session.commit()
    monkeypatch.setattr(world_gen, "get_tile_type", lambda x, y: "grass")

    founded = expansion.found_settlement(
        db_session,
        user,
        city,
        "Segunda Ciudad",
        30,
        31,
        "city",
    )

    db_session.refresh(membership)
    db_session.refresh(city)
    assert founded.settlement_type == "city"
    assert founded.population_max == balance.CITY_POPULATION_MAX
    assert membership.expansion_points == 0
    for resource in balance.RESOURCE_FIELDS:
        assert getattr(founded, resource) == pytest.approx(
            balance.CITY_STARTING_RESOURCES[resource]
        )
        assert getattr(city, resource) == pytest.approx(
            1000.0 - balance.CITY_FOUNDING_COST.get(resource, 0.0),
            abs=0.1,
        )


def test_camp_cannot_found_recursive_settlement(db_session, user, city):
    _membership(db_session, user, city, points=10)
    camp = models.City(
        name="Origin Camp",
        owner_id=user.id,
        world_id=city.world_id,
        x=40,
        y=40,
        settlement_type="camp",
    )
    _set_resources(camp, 5000)
    db_session.add(camp)
    db_session.commit()

    with pytest.raises(ValueError, match="Only a full city"):
        expansion.found_settlement(
            db_session,
            user,
            camp,
            "Recursive Camp",
            41,
            41,
            "camp",
        )


def test_expansion_status_is_world_scoped(db_session, user, city):
    membership = _membership(db_session, user, city, points=7)
    db_session.add(
        models.City(
            name="Owned Camp",
            owner_id=user.id,
            world_id=city.world_id,
            x=50,
            y=50,
            settlement_type="camp",
        )
    )
    db_session.commit()

    status = expansion.get_expansion_status(
        db_session,
        user_id=user.id,
        world_id=city.world_id,
    )

    assert status["expansion_points"] == membership.expansion_points == 7
    assert status["city_count"] == 1
    assert status["camp_count"] == 1
    assert status["point_costs"] == balance.SETTLEMENT_EXPANSION_POINT_COSTS

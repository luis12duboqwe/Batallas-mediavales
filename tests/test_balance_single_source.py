import pytest

from app import models
from app.routers import wiki
from app.services import (
    balance,
    building,
    combat,
    economy,
    market,
    movement,
    production,
    research,
    troops,
    tutorial,
    unit_catalog,
)


def test_live_services_reference_canonical_balance_objects():
    assert building.BUILDING_COSTS is balance.BUILDING_COSTS
    assert building.BUILDING_PREREQUISITES is balance.BUILDING_PREREQUISITES
    assert production.PRODUCTION_RATES is balance.PRODUCTION_RATES_PER_HOUR
    assert unit_catalog.UNIT_CATALOG is balance.UNIT_CATALOG
    assert unit_catalog.UNIT_ORDER is balance.UNIT_ORDER
    assert movement.UNIT_SPEED is balance.UNIT_SPEED
    assert movement.RESOURCE_FIELDS is balance.RESOURCE_FIELDS
    assert tutorial.TUTORIAL_REWARD is balance.TUTORIAL_REWARD

    assert building.REFUND_FACTOR == balance.QUEUE_REFUND_FACTOR
    assert research.REFUND_FACTOR == balance.QUEUE_REFUND_FACTOR
    assert troops.REFUND_FACTOR == balance.QUEUE_REFUND_FACTOR
    assert market.MARKET_BUILDING_NAME == balance.MARKET_BUILDING_KEY
    assert market.MERCHANT_CAPACITY == balance.MERCHANT_CAPACITY_PER_LEVEL
    assert market.TRANSPORT_BASE_SPEED == balance.TRANSPORT_BASE_SPEED
    assert combat.WALL_NAME == balance.WALL_BUILDING_KEY == "wall"

    for unit_type in balance.UNIT_ORDER:
        assert combat.UNIT_STATS[unit_type] == balance.UNIT_COMBAT_STATS[unit_type]


def test_compatibility_economy_matches_live_services():
    for target_level in (1, 2, 5):
        assert economy.get_building_cost("barracks", target_level) == (
            building.calculate_upgrade_cost("barracks", target_level)
        )

    for unit_type in balance.UNIT_ORDER:
        definition = balance.UNIT_CATALOG[unit_type]
        assert economy.get_troop_cost(unit_type, 2) == {
            resource: amount * 2
            for resource, amount in definition["training_cost"].items()
        }
        assert economy.get_training_time(unit_type, 20) == definition[
            "training_time_seconds"
        ]


def test_real_wall_receives_canonical_defense_bonus(db_session, second_city):
    db_session.add(models.Building(city_id=second_city.id, name="wall", level=4))
    db_session.commit()
    db_session.expire(second_city, ["buildings"])

    assert combat._wall_bonus(second_city) == pytest.approx(
        1.0 + 4 * balance.WALL_BONUS_PER_LEVEL
    )


def test_balance_snapshot_is_mounted_and_versioned(client):
    response = client.get("/economy/balance_preview")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["version"] == balance.BALANCE_VERSION
    assert payload["buildings"]["cost_growth"] == balance.BUILDING_COST_GROWTH
    assert payload["buildings"]["catalog"]["academy"]["max_level"] == (
        balance.BUILDING_MAX_LEVELS["academy"]
    )
    assert payload["buildings"]["catalog"]["academy"]["effect"] == (
        balance.get_building_effect_definition("academy")
    )
    assert payload["production"]["base_rates_per_hour"] == (
        balance.PRODUCTION_RATES_PER_HOUR
    )
    assert payload["production"]["population_per_farm_level"] == (
        balance.POPULATION_PER_FARM_LEVEL
    )
    assert payload["units"]["catalog"]["archer"]["training_cost"] == (
        balance.UNIT_CATALOG["archer"]["training_cost"]
    )
    assert payload["units"]["catalog"]["archer"]["research_time_seconds"] == (
        balance.UNIT_CATALOG["archer"]["research_time_seconds"]
    )
    assert payload["units"]["research_queue_slots_per_city"] == (
        balance.RESEARCH_QUEUE_SLOTS_PER_CITY
    )
    assert payload["units"]["catalog"]["spy"]["movement_speed"] == (
        movement.UNIT_SPEED["spy"]
    )
    noble = payload["units"]["catalog"]["noble"]
    assert noble["population"] == balance.UNIT_CATALOG["noble"]["population"] == 5
    assert noble["upkeep_per_hour"] == pytest.approx(
        balance.UNIT_CATALOG["noble"]["upkeep_per_hour"]
    )
    assert noble["movement_speed"] == balance.UNIT_SPEED["noble"]
    assert noble["combat"] == balance.UNIT_COMBAT_STATS["noble"]
    assert payload["market"]["merchant_capacity_per_level"] == (
        market.MERCHANT_CAPACITY
    )
    assert payload["tutorial"]["completion_reward"] == balance.TUTORIAL_REWARD
    assert payload["pve_alpha"]["barbarian_starting_resources"] == (
        balance.BARBARIAN_STARTING_RESOURCES
    )


def test_public_balance_views_use_same_version(client):
    troops_response = client.get("/public-api/troops")
    buildings_response = client.get("/public-api/buildings")

    assert troops_response.status_code == 200, troops_response.text
    assert buildings_response.status_code == 200, buildings_response.text
    assert troops_response.json()["version"] == balance.BALANCE_VERSION
    assert buildings_response.json()["version"] == balance.BALANCE_VERSION
    assert troops_response.json()["catalog"]["spy"]["movement_speed"] == (
        balance.UNIT_SPEED["spy"]
    )
    assert troops_response.json()["catalog"]["heavy_infantry"]["research_cost"]["gold"] > 0
    assert troops_response.json()["catalog"]["noble"]["upkeep_per_hour"] == pytest.approx(
        balance.UNIT_CATALOG["noble"]["upkeep_per_hour"]
    )
    assert buildings_response.json()["cost_growth"] == balance.BUILDING_COST_GROWTH
    assert buildings_response.json()["catalog"]["academy"]["display_name"] == (
        balance.BUILDING_DISPLAY_NAMES["academy"]
    )


def test_builtin_help_is_generated_from_current_balance():
    troop_article = wiki._build_troop_article()
    research_article = wiki._build_research_article()
    building_article = wiki._build_building_article()
    economy_article = wiki._build_economy_article()
    combat_article = wiki._build_combat_article()
    espionage_article = wiki._build_espionage_article()
    conquest_article = wiki._build_conquest_article()
    beginner_article = wiki._build_beginner_article()

    combined = "\n".join(
        [
            troop_article,
            research_article,
            building_article,
            economy_article,
            combat_article,
            espionage_article,
            conquest_article,
            beginner_article,
        ]
    )

    assert balance.BALANCE_VERSION in combined
    assert "Madera/Piedra/Hierro/Oro" in combined
    assert "Mant. oro/h" in troop_article
    assert "Pobl." in troop_article
    noble = balance.UNIT_CATALOG["noble"]
    assert f"| {int(noble['population'])} | {float(noble['upkeep_per_hour']):g} |" in troop_article
    assert "Las tropas consumen oro por hora incluso mientras viajan o regresan" in troop_article
    assert "eventos temporales no autorizan un ejército permanente mayor" in troop_article
    assert "Academia Militar" in research_article
    assert str(balance.UNIT_CATALOG["heavy_infantry"]["research_time_seconds"]) in research_article
    assert f"{balance.QUEUE_REFUND_FACTOR * 100:.0f}%" in research_article
    assert "tiempo_base_del_edificio * nivel_objetivo" in building_article
    assert str(balance.POPULATION_PER_FARM_LEVEL) in building_article
    assert "1.26" not in combined
    assert "1.18" not in combined
    assert "Aserradero" not in beginner_article
    assert "Cantera" not in beginner_article
    assert "Mina Profunda" not in beginner_article
    assert "conquista PvP está deshabilitada" in conquest_article
    assert "loot_modifier" in combat_article
    assert "≥5" not in espionage_article
    assert "recursos, tropas y niveles de edificios" in espionage_article

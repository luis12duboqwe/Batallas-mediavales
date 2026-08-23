import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "batalla_medieval_backend"


def _decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def test_four_resource_migration_preserves_legacy_economy_and_rolls_back(tmp_path, monkeypatch):
    database_path = tmp_path / "four-resources.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(os, "urandom", lambda size: bytes(size))

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "0006")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO worlds (
                    id, name, speed_modifier, resource_modifier, map_size,
                    special_rules, created_at, is_active
                ) VALUES (1, 'Legacy World', 1.0, 1.0, 100, '', CURRENT_TIMESTAMP, 1)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO cities (
                    id, name, owner_id, world_id, x, y, wood, clay, iron,
                    loyalty, population_max, last_production, researched_units, tile_type
                ) VALUES (
                    1, 'Legacy City', NULL, 1, 3, 4, 111.0, 432.5, 222.0,
                    100.0, 100, CURRENT_TIMESTAMP, :researched, 'grass'
                )
                """
            ),
            {"researched": json.dumps(["basic_infantry"])},
        )
        connection.execute(
            text(
                """
                INSERT INTO market_offers (
                    id, city_id, world_id, offer_type, offer_amount,
                    request_type, request_amount, is_alliance_only, created_at
                ) VALUES (1, 1, 1, 'clay', 25, 'wood', 10, 0, CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO movements (
                    id, origin_city_id, target_city_id, target_oasis_id, world_id,
                    movement_type, troops, resources, spy_count, arrival_time,
                    created_at, speed_used, status, target_building
                ) VALUES (
                    1, 1, 1, NULL, 1, 'transport', :troops, :resources, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1.0, 'ongoing', NULL
                )
                """
            ),
            {
                "troops": json.dumps({}),
                "resources": json.dumps({"wood": 10, "clay": 25, "iron": 5}),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO building_queue (
                    id, city_id, building_type, target_level, finish_time, paid_cost
                ) VALUES (1, 1, 'warehouse', 2, CURRENT_TIMESTAMP, :paid_cost)
                """
            ),
            {"paid_cost": json.dumps({"wood": 20, "clay": 30, "iron": 10})},
        )
        connection.execute(
            text(
                """
                INSERT INTO troop_queue (
                    id, city_id, troop_type, amount, finish_time, paid_cost
                ) VALUES (1, 1, 'basic_infantry', 1, CURRENT_TIMESTAMP, :paid_cost)
                """
            ),
            {"paid_cost": json.dumps({"wood": 5, "clay": 3, "iron": 2})},
        )
        connection.execute(
            text(
                """
                INSERT INTO oases (
                    id, world_id, x, y, resource_type, bonus_percent, owner_city_id, troops
                ) VALUES (1, 1, 8, 8, 'clay', 25, NULL, :troops)
                """
            ),
            {"troops": json.dumps({})},
        )
        connection.execute(
            text(
                """
                INSERT INTO quests (
                    id, quest_id, title, description, requirements, reward, is_tutorial
                ) VALUES (
                    1, 'legacy-resource', 'Legacy', 'Legacy resource quest',
                    :requirements, :reward, 1
                )
                """
            ),
            {
                "requirements": json.dumps({"resource": "clay", "amount": 10}),
                "reward": json.dumps({"clay": 15}),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO reports (
                    id, city_id, world_id, report_type, content, created_at,
                    attacker_city_id, defender_city_id
                ) VALUES (
                    1, 1, 1, 'battle', :content, CURRENT_TIMESTAMP, 1, 1
                )
                """
            ),
            {"content": json.dumps({"loot": {"clay": 12, "wood": 2}})},
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    city_columns = {column["name"] for column in inspector.get_columns("cities")}
    assert "stone" in city_columns
    assert "gold" in city_columns
    assert "clay" not in city_columns

    with engine.connect() as connection:
        city = connection.execute(text("SELECT wood, stone, iron, gold FROM cities WHERE id = 1")).one()
        assert tuple(city) == (111.0, 432.5, 222.0, 500.0)

        offer = connection.execute(
            text("SELECT offer_type, request_type FROM market_offers WHERE id = 1")
        ).one()
        assert tuple(offer) == ("stone", "wood")
        assert connection.execute(text("SELECT resource_type FROM oases WHERE id = 1")).scalar_one() == "stone"

        movement = _decoded(connection.execute(text("SELECT resources FROM movements WHERE id = 1")).scalar_one())
        building_cost = _decoded(connection.execute(text("SELECT paid_cost FROM building_queue WHERE id = 1")).scalar_one())
        troop_cost = _decoded(connection.execute(text("SELECT paid_cost FROM troop_queue WHERE id = 1")).scalar_one())
        quest_reward = _decoded(connection.execute(text("SELECT reward FROM quests WHERE id = 1")).scalar_one())
        quest_requirements = _decoded(connection.execute(text("SELECT requirements FROM quests WHERE id = 1")).scalar_one())
        report = json.loads(connection.execute(text("SELECT content FROM reports WHERE id = 1")).scalar_one())

        assert movement == {"wood": 10, "stone": 25, "iron": 5}
        assert building_cost == {"wood": 20, "stone": 30, "iron": 10}
        assert troop_cost == {"wood": 5, "stone": 3, "iron": 2}
        assert quest_reward == {"stone": 15}
        assert quest_requirements == {"resource": "stone", "amount": 10}
        assert report["loot"] == {"stone": 12, "wood": 2}
    engine.dispose()

    command.downgrade(config, "0006")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    city_columns = {column["name"] for column in inspector.get_columns("cities")}
    assert "clay" in city_columns
    assert "stone" not in city_columns
    assert "gold" not in city_columns
    with engine.connect() as connection:
        assert connection.execute(text("SELECT clay FROM cities WHERE id = 1")).scalar_one() == 432.5
        assert connection.execute(text("SELECT offer_type FROM market_offers WHERE id = 1")).scalar_one() == "clay"
        movement = _decoded(connection.execute(text("SELECT resources FROM movements WHERE id = 1")).scalar_one())
        assert movement == {"wood": 10, "clay": 25, "iron": 5}
        report = json.loads(connection.execute(text("SELECT content FROM reports WHERE id = 1")).scalar_one())
        assert report["loot"] == {"clay": 12, "wood": 2}
    engine.dispose()

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "batalla_medieval_backend"


def test_expansion_migration_preserves_existing_cities_and_memberships(tmp_path, monkeypatch):
    database_path = tmp_path / "expansion.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "0007")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO worlds (
                    id, name, speed_modifier, resource_modifier, map_size,
                    special_rules, created_at, is_active
                ) VALUES (1, 'Expansion Legacy', 1.0, 1.0, 100, '', CURRENT_TIMESTAMP, 1)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO cities (
                    id, name, owner_id, world_id, x, y, wood, stone, iron, gold,
                    loyalty, population_max, last_production, researched_units, tile_type
                ) VALUES (
                    1, 'Existing City', NULL, 1, 3, 4, 111.0, 222.0, 333.0, 444.0,
                    100.0, 100, CURRENT_TIMESTAMP, '[]', 'grass'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO player_world (
                    id, user_id, world_id, starting_city_id, joined_at
                ) VALUES (1, 999, 1, NULL, CURRENT_TIMESTAMP)
                """
            )
        )

    command.upgrade(config, "head")

    inspector = inspect(engine)
    city_columns = {column["name"] for column in inspector.get_columns("cities")}
    membership_columns = {
        column["name"] for column in inspector.get_columns("player_world")
    }
    assert "settlement_type" in city_columns
    assert "expansion_points" in membership_columns

    with engine.connect() as connection:
        settlement_type = connection.execute(
            text("SELECT settlement_type FROM cities WHERE id = 1")
        ).scalar_one()
        expansion_points = connection.execute(
            text("SELECT expansion_points FROM player_world WHERE id = 1")
        ).scalar_one()
    assert settlement_type == "city"
    assert expansion_points == 0

    command.downgrade(config, "0007")
    inspector = inspect(engine)
    assert "settlement_type" not in {
        column["name"] for column in inspector.get_columns("cities")
    }
    assert "expansion_points" not in {
        column["name"] for column in inspector.get_columns("player_world")
    }

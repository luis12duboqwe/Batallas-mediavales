from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "batalla_medieval_backend"


def test_research_queue_migration_preserves_completed_research_and_rolls_back(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "research-queue.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "0008")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO worlds (
                    id, name, speed_modifier, resource_modifier, map_size,
                    special_rules, created_at, is_active
                ) VALUES (1, 'Research Legacy', 1.0, 1.0, 100, '', CURRENT_TIMESTAMP, 1)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO cities (
                    id, name, owner_id, world_id, x, y, settlement_type,
                    wood, stone, iron, gold, loyalty, population_max,
                    last_production, researched_units, tile_type
                ) VALUES (
                    1, 'Existing Research City', NULL, 1, 3, 4, 'city',
                    1000.0, 1000.0, 1000.0, 1000.0, 100.0, 100,
                    CURRENT_TIMESTAMP, '["basic_infantry", "spy"]', 'grass'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO research (id, city_id, tech_name, level)
                VALUES (1, 1, 'spy', 1)
                """
            )
        )

    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert "research_queue" in inspector.get_table_names()
    indexes = {index["name"]: index for index in inspector.get_indexes("research_queue")}
    assert indexes["ux_research_queue_city"]["unique"] == 1
    assert indexes["ux_research_queue_city_tech"]["unique"] == 1

    with engine.begin() as connection:
        completed = connection.execute(
            text("SELECT tech_name, level FROM research WHERE city_id = 1")
        ).one()
        assert completed.tech_name == "spy"
        assert completed.level == 1

        connection.execute(
            text(
                """
                INSERT INTO research_queue (city_id, tech_name, finish_time, paid_cost)
                VALUES (1, 'heavy_infantry', CURRENT_TIMESTAMP,
                        '{"wood":500,"stone":400,"iron":300,"gold":50}')
                """
            )
        )
        assert connection.execute(text("SELECT COUNT(*) FROM research_queue")).scalar_one() == 1

    command.downgrade(config, "0008")
    inspector = inspect(engine)
    assert "research_queue" not in inspector.get_table_names()

    with engine.connect() as connection:
        completed_after = connection.execute(
            text("SELECT tech_name, level FROM research WHERE city_id = 1")
        ).one()
    assert completed_after.tech_name == "spy"
    assert completed_after.level == 1

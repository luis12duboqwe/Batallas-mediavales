import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "batalla_medieval_backend"


def test_initial_migration_upgrade_check_and_downgrade(tmp_path, monkeypatch):
    database_path = tmp_path / "migration-test.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    # The workspace runner has no usable /dev/urandom. This patch is scoped to
    # this test and is harmless on normal CI runners.
    monkeypatch.setattr(os, "urandom", lambda size: bytes(size))

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"users", "worlds", "alliances", "cities", "movements"} <= tables

    world_foreign_keys = {
        foreign_key["name"] for foreign_key in inspector.get_foreign_keys("worlds")
    }
    assert "fk_worlds_winner_id_users" in world_foreign_keys
    assert "fk_worlds_winner_alliance_id_alliances" in world_foreign_keys

    command.check(config)
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(database_url)
    remaining_tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert not (remaining_tables - {"alembic_version"})


def test_0005_promotes_legacy_researched_json_to_canonical_rows(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy-research.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(os, "urandom", lambda size: bytes(size))

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "0004")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO worlds (
                    id, name, speed_modifier, resource_modifier, map_size,
                    special_rules, created_at, is_active
                ) VALUES (
                    1, 'Legacy World', 1.0, 1.0, 100,
                    '', CURRENT_TIMESTAMP, 1
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO cities (
                    id, name, owner_id, world_id, x, y,
                    wood, clay, iron, loyalty, population_max,
                    last_production, researched_units, tile_type
                ) VALUES (
                    1, 'Legacy City', NULL, 1, 3, 4,
                    500.0, 500.0, 500.0, 100.0, 100,
                    CURRENT_TIMESTAMP, :researched_units, 'grass'
                )
                """
            ),
            {"researched_units": json.dumps(["basic_infantry", "spy"])},
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        researched = connection.execute(
            text(
                "SELECT tech_name, level FROM research "
                "WHERE city_id = 1 ORDER BY tech_name"
            )
        ).all()
        raw_units = connection.execute(
            text("SELECT researched_units FROM cities WHERE id = 1")
        ).scalar_one()

    units = json.loads(raw_units) if isinstance(raw_units, str) else list(raw_units)
    assert researched == [("spy", 1)]
    assert units == ["basic_infantry", "spy"]
    engine.dispose()

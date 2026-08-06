import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


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

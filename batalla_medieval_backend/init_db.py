"""Compatibility entry point for initializing or upgrading the database."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    config = Config(str(Path(__file__).with_name("alembic.ini")))
    command.upgrade(config, "head")
    print("Database is at the latest migration revision.")


if __name__ == "__main__":
    main()

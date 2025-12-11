from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _add_column_if_missing(connection, inspector, table_name: str, column_name: str, ddl: str) -> None:
    if table_name not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in existing_columns:
        return

    connection.execute(text(ddl))


def run_migrations(engine: Engine) -> None:
    """Ensure the database schema matches newly added model columns.

    This lightweight migration runner is intended to patch existing databases where
    ``Base.metadata.create_all`` would otherwise leave out new columns that were
    introduced after the initial deployment.
    """

    with engine.begin() as connection:
        inspector = inspect(connection)

        _add_column_if_missing(
            connection,
            inspector,
            "cities",
            "population_max",
            "ALTER TABLE cities ADD COLUMN population_max INTEGER DEFAULT 100",
        )

        _add_column_if_missing(
            connection,
            inspector,
            "users",
            "is_admin",
            "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0",
        )

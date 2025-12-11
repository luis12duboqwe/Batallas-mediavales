from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def run_migrations() -> None:
    """
    Ensure database schema matches the current models.

    SQLAlchemy's ``create_all`` does not alter existing tables, so we run a
    lightweight migration to add newly introduced columns when they are
    missing. This keeps existing deployments functional after model updates.
    """

    # Create missing tables first.
    Base.metadata.create_all(bind=engine)

    # Add ``users.protection_ends_at`` if the table already exists without it.
    with engine.begin() as connection:
        inspector = inspect(connection)
        user_columns = {column["name"] for column in inspector.get_columns("users")}

        if "protection_ends_at" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN protection_ends_at TIMESTAMP")
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

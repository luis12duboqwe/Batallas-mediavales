from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def run_message_migrations(engine: Engine) -> None:
    """Ensure the messages table matches the current Message model.

    This lightweight migration keeps existing deployments working without a
    dedicated migration framework by adding the new columns used by the
    Message model when they are missing and migrating values from the
    previous schema.
    """

    inspector = inspect(engine)

    if not inspector.has_table("messages"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("messages")}

    with engine.begin() as connection:
        if "receiver_id" not in existing_columns:
            connection.execute(text("ALTER TABLE messages ADD COLUMN receiver_id INTEGER"))
            if "recipient_id" in existing_columns:
                connection.execute(
                    text(
                        "UPDATE messages SET receiver_id = recipient_id "
                        "WHERE receiver_id IS NULL"
                    )
                )

        if "subject" not in existing_columns:
            connection.execute(
                text("ALTER TABLE messages ADD COLUMN subject VARCHAR(255) DEFAULT ''")
            )

        if "read" not in existing_columns:
            connection.execute(
                text("ALTER TABLE messages ADD COLUMN read BOOLEAN DEFAULT 0")
            )

        if "timestamp" not in existing_columns:
            connection.execute(text("ALTER TABLE messages ADD COLUMN timestamp DATETIME"))
            if "sent_at" in existing_columns:
                connection.execute(
                    text(
                        "UPDATE messages SET timestamp = sent_at WHERE timestamp IS NULL"
                    )
                )
            connection.execute(
                text("UPDATE messages SET timestamp = CURRENT_TIMESTAMP WHERE timestamp IS NULL")
            )

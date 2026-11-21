#!/usr/bin/env python3
"""Print a non-PII, read-only impact report for one historical Wonder world.

Example from a controlled operator shell (not from public traffic):
    DATABASE_URL=... python scripts/audit_legacy_wonder.py --world-id 1

Never pass credentials as CLI args. A report does not authorize conversion.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

# Run from repository root without global backend-package installation.
BACKEND_ROOT = Path(__file__).resolve().parents[1] / "batalla_medieval_backend"
sys.path.insert(0, str(BACKEND_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only legacy Wonder impact audit")
    parser.add_argument("--world-id", required=True, type=int, help="Positive historical world ID")
    args = parser.parse_args(argv)
    if args.world_id < 1:
        parser.error("--world-id must be a positive integer")

    # Never use Settings' implicit development SQLite URL or create a new
    # SQLite file while pretending to audit a real, existing world.
    raw_url = os.environ.get("DATABASE_URL", "").strip()
    if not raw_url:
        print("Wonder audit refused: explicit DATABASE_URL is required", file=sys.stderr)
        return 2

    # Initialization failures (including Pydantic ValidationError, which
    # subclasses ValueError) can echo DATABASE_URL and other secrets.
    # Only deliberate ValueErrors from the audit service may be printed.
    from sqlalchemy import inspect
    from sqlalchemy.engine import make_url

    try:
        url = make_url(raw_url)
        if url.get_backend_name() == "sqlite":
            database = url.database
            if database in (None, "", ":memory:") or not Path(database).is_file():
                print(
                    "Wonder audit refused: existing SQLite database file required",
                    file=sys.stderr,
                )
                return 2
        from app.database import SessionLocal
        from app.services.wonder_transition_audit import audit_legacy_wonder_transition

        db = SessionLocal()
        try:
            inspector = inspect(db.get_bind())
            required = {"wonder_funding", "wonder_contributions", "worlds", "player_world"}
            if not all(inspector.has_table(table) for table in required) or (
                "wonder_rules_version"
                not in {column["name"] for column in inspector.get_columns("worlds")}
            ):
                print(
                    "Wonder audit refused: database requires Alembic 0020 or later",
                    file=sys.stderr,
                )
                return 2

            try:
                report = audit_legacy_wonder_transition(db, args.world_id)
            except ValueError as exc:
                # This is the sole trustworthy, human-readable error source.
                print(f"Wonder audit refused: {exc}", file=sys.stderr)
                return 2
            print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        finally:
            # No commit: close and roll back any open read transaction.
            db.close()
    except Exception:
        # Do not surface raw DB exceptions, Settings ValidationError, SQL
        # parameters, passwords or malformed connection strings.
        print(
            "Wonder audit refused: invalid configuration, permissions or database connection",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

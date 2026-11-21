#!/usr/bin/env python3
"""Print a non-PII, read-only impact report for one historical Wonder world.

Example from a controlled operator shell (not from public traffic):
    python scripts/audit_legacy_wonder.py --world-id 1

DATABASE_URL is read from the normal app environment; never pass credentials
on the command line. A report does not authorize a conversion or deploy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Keep the tool runnable from the repository root without installing the
# backend package into an operator's global Python environment.
BACKEND_ROOT = Path(__file__).resolve().parents[1] / "batalla_medieval_backend"
sys.path.insert(0, str(BACKEND_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only legacy Wonder impact audit")
    parser.add_argument("--world-id", required=True, type=int, help="Positive historical world ID")
    args = parser.parse_args(argv)
    if args.world_id < 1:
        parser.error("--world-id must be a positive integer")

    from app.database import SessionLocal
    from app.services.wonder_transition_audit import audit_legacy_wonder_transition

    db = SessionLocal()
    try:
        report = audit_legacy_wonder_transition(db, args.world_id)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    except ValueError as exc:
        print(f"Wonder audit refused: {exc}", file=sys.stderr)
        return 2
    finally:
        # Close without commit; SQLAlchemy rolls back any read transaction.
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

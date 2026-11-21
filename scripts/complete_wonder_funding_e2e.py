"""Finish one Wonder queue in disposable browser E2E SQLite only.

This is a test fixture, never an administrative or production completion tool.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.services import building
from app.utils import utc_now


def main() -> None:
    source = os.environ.get("PARALLEL_JOURNEY_DB", "")
    db_url = os.environ.get("DATABASE_URL", "")
    path = Path(source).resolve() if source else None
    if (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("PARALLEL_JOURNEY_ALLOW_MUTATIONS") != "isolated"
        or path is None
        or not str(path).startswith("/tmp/medievol-journey-ci-wonder-")
        or not path.is_file()
        or db_url != "sqlite:///" + str(path)
    ):
        raise RuntimeError("Only the disposable Wonder journey SQLite is allowed")
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        raise ValueError("Expected a synthetic target city id")
    city_id = int(sys.argv[1])
    if city_id < 1:
        raise ValueError("Invalid synthetic city id")

    db = SessionLocal()
    try:
        city = db.get(models.City, city_id)
        if city is None or city.world.wonder_rules_version != "alliance-v2":
            raise RuntimeError("Only the active test Wonder world may be completed")
        pending = (
            db.query(models.BuildingQueue)
            .filter_by(city_id=city_id, building_type="world_wonder", target_level=1)
            .one()
        )
        escrow = (
            db.query(models.WonderFunding)
            .filter_by(city_id=city_id, target_level=1, status="queued")
            .one()
        )
        if any(getattr(escrow, "funded_" + resource) == 0 for resource in ("wood", "stone", "iron", "gold")):
            raise RuntimeError("Unfunded project cannot be completed")
        pending.finish_time = utc_now() - timedelta(seconds=5)
        db.commit()
        building.process_building_queues(db)
        db.expire_all()
        completed = db.query(models.Building).filter_by(
            city_id=city_id, name="world_wonder",
        ).one()
        escrow = db.get(models.WonderFunding, escrow.id)
        if completed.level != 1 or escrow.status != "completed":
            raise AssertionError("Worker did not complete the funded Wonder level")
        if db.query(models.BuildingQueue).filter_by(
            city_id=city_id, building_type="world_wonder",
        ).count() != 0:
            raise AssertionError("Completed Wonder still has a queued upgrade")
        print("WONDER_ISOLATED_WORKER_COMPLETE level=1 status=completed")
    finally:
        db.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import balance, production, unit_catalog, world_lifecycle

logger = logging.getLogger(__name__)
REFUND_FACTOR = balance.QUEUE_REFUND_FACTOR


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_researched_techs(db: Session, city_id: int):
    return db.query(models.Research).filter(models.Research.city_id == city_id).all()


def is_researched(db: Session, city_id: int, tech_name: str) -> bool:
    return unit_catalog.is_researched(db, city_id, tech_name)


def _sync_city_researched_units(db: Session, city: models.City) -> None:
    """Keep the legacy City JSON mirror aligned without deleting old progress."""

    researched = ["basic_infantry"]
    researched.extend(
        unit
        for unit in list(city.researched_units or [])
        if unit != "basic_infantry"
    )
    researched.extend(
        row.tech_name
        for row in (
            db.query(models.Research)
            .filter(models.Research.city_id == city.id)
            .order_by(models.Research.id.asc())
            .all()
        )
        if row.tech_name != "basic_infantry"
    )
    city.researched_units = list(dict.fromkeys(researched))
    db.add(city)


def queue_research(
    db: Session,
    city: models.City,
    tech_name: str,
) -> models.ResearchQueue:
    """Charge and queue one technology without unlocking it early."""

    world_lifecycle.require_world_open(db, city.world_id)

    definition = unit_catalog.get_unit(tech_name)
    if not definition["researchable"]:
        raise ValueError("Technology is already available by default")

    city, production_gains = production.lock_and_recalculate_resources(db, city)
    db.expire(city, ["buildings"])

    if is_researched(db, city.id, tech_name):
        db.rollback()
        raise ValueError("Technology already researched")

    active_queue = (
        db.query(models.ResearchQueue)
        .filter(models.ResearchQueue.city_id == city.id)
        .with_for_update()
        .one_or_none()
    )
    if active_queue is not None:
        db.rollback()
        if active_queue.tech_name == tech_name:
            raise ValueError("Technology research already queued")
        raise ValueError("Research queue is already occupied")

    missing = unit_catalog.first_missing_requirement(
        city, definition["research_requirements"]
    )
    if missing:
        req_name, req_level = missing
        db.rollback()
        raise ValueError(
            f"Prerequisite not met: {req_name} level {req_level} required"
        )

    cost = definition["research_cost"]
    if not production.check_cost(city, cost):
        db.rollback()
        raise ValueError("Insufficient resources")

    duration = int(definition.get("research_time_seconds", 0))
    if duration <= 0:
        db.rollback()
        raise ValueError("Research duration is not configured")

    production.pay_cost(city, cost)
    queue_entry = models.ResearchQueue(
        city_id=city.id,
        tech_name=tech_name,
        finish_time=utc_now() + timedelta(seconds=duration),
        paid_cost={resource: float(amount) for resource, amount in cost.items()},
    )
    db.add(queue_entry)
    db.commit()
    db.refresh(queue_entry)
    production.record_resource_gains(db, city, production_gains)
    logger.info(
        "research_queued",
        extra={
            "city_id": city.id,
            "tech_name": tech_name,
            "finish_time": queue_entry.finish_time.isoformat(),
            "paid_cost": queue_entry.paid_cost,
        },
    )
    return queue_entry


def process_research_queues(db: Session) -> list[dict]:
    """Complete each due research queue at most once."""

    now = utc_now()
    due = (
        db.query(models.ResearchQueue)
        .filter(
            models.ResearchQueue.finish_time <= now,
            models.ResearchQueue.city_id.in_(
                db.query(models.City.id).filter(
                    models.City.world_id.in_(
                        db.query(models.World.id).filter(models.World.lifecycle_status == "open")
                    )
                )
            ),
        )
        .order_by(models.ResearchQueue.id.asc())
        .with_for_update(skip_locked=True)
        .all()
    )
    if not due:
        return []

    completed: list[dict] = []
    for queue_entry in due:
        city = (
            db.query(models.City)
            .filter(models.City.id == queue_entry.city_id)
            .with_for_update()
            .one_or_none()
        )
        if city is None:
            db.delete(queue_entry)
            continue

        existing = (
            db.query(models.Research)
            .filter(
                models.Research.city_id == city.id,
                models.Research.tech_name == queue_entry.tech_name,
            )
            .with_for_update()
            .one_or_none()
        )
        if existing is None:
            db.add(
                models.Research(
                    city_id=city.id,
                    tech_name=queue_entry.tech_name,
                    level=1,
                )
            )
            db.flush()
            _sync_city_researched_units(db, city)

        completed.append(
            {
                "city_id": city.id,
                "tech_name": queue_entry.tech_name,
                "owner_id": city.owner_id,
                "world_id": city.world_id,
            }
        )
        db.delete(queue_entry)

    db.commit()
    logger.info(
        "research_queues_completed",
        extra={
            "count": len(completed),
            "cities": [item["city_id"] for item in completed],
        },
    )
    return completed


def cancel_research_queue(db: Session, queue_id: int, user_id: int) -> bool:
    """Cancel future research and refund 80% of the exact recorded cost."""

    queue_entry = (
        db.query(models.ResearchQueue)
        .join(models.City)
        .filter(
            models.ResearchQueue.id == queue_id,
            models.City.owner_id == user_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if queue_entry is None:
        return False

    queue_city = db.query(models.City).filter(models.City.id == queue_entry.city_id).one()
    world_lifecycle.require_world_open(db, queue_city.world_id)

    if _as_utc(queue_entry.finish_time) <= _as_utc(utc_now()):
        db.rollback()
        raise ValueError("Completed research queue can no longer be cancelled")

    city, production_gains = production.lock_and_recalculate_resources(
        db, queue_entry.city_id
    )
    definition = unit_catalog.get_unit(queue_entry.tech_name)
    paid_cost = queue_entry.paid_cost or definition["research_cost"]
    storage_limit = production.get_storage_limit(city)

    for resource, amount in paid_cost.items():
        current = float(getattr(city, resource))
        if current >= storage_limit:
            continue
        setattr(
            city,
            resource,
            min(current + float(amount) * REFUND_FACTOR, storage_limit),
        )

    db.delete(queue_entry)
    db.commit()
    production.record_resource_gains(db, city, production_gains)
    logger.info(
        "research_cancelled",
        extra={
            "city_id": city.id,
            "tech_name": queue_entry.tech_name,
            "queue_id": queue_id,
        },
    )
    return True


def research_tech(db: Session, city: models.City, tech_name: str) -> models.ResearchQueue:
    """Compatibility entrypoint: research now means queueing, never instant unlock."""

    return queue_research(db, city, tech_name)

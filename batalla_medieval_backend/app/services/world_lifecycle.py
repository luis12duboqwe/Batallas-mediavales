"""Server-authoritative BM-0072 world lifecycle transitions."""

from __future__ import annotations

from datetime import timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import admin as admin_service

WORLD_STATES = {"draft", "open", "paused", "closed", "archived"}
ALLOWED_TRANSITIONS = {
    "draft": {"open"},
    "open": {"paused", "closed"},
    "paused": {"open", "closed"},
    "closed": {"archived"},
    "archived": set(),
}


def require_world_open(db: Session, world_id: int, *, lock: bool = True) -> models.World:
    query = db.query(models.World).filter(
        models.World.id == world_id,
        models.World.lifecycle_status == "open",
        models.World.is_active.is_(True),
    )
    if lock:
        query = query.with_for_update().populate_existing()
    world = query.one_or_none()
    if world is None:
        raise ValueError("World is not open")
    return world


def require_world_open_http(db: Session, world_id: int, *, lock: bool = True) -> models.World:
    try:
        return require_world_open(db, world_id, lock=lock)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="World is not open") from exc


def _aware(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _lock_world_clock_rows(db: Session, world: models.World):
    movements = (
        db.query(models.Movement)
        .filter(
            models.Movement.world_id == world.id,
            models.Movement.status == "ongoing",
        )
        .with_for_update()
        .all()
    )

    cities = (
        db.query(models.City)
        .filter(models.City.world_id == world.id)
        .with_for_update()
        .all()
    )
    city_ids = [city.id for city in cities]

    queue_rows = []
    if city_ids:
        for model in (models.BuildingQueue, models.TroopQueue, models.ResearchQueue):
            queue_rows.extend(
                db.query(model)
                .filter(model.city_id.in_(city_ids))
                .with_for_update()
                .all()
            )

    adventures = (
        db.query(models.Adventure)
        .join(models.Hero, models.Adventure.hero_id == models.Hero.id)
        .filter(
            models.Hero.world_id == world.id,
            models.Adventure.status == "active",
            models.Adventure.started_at.is_not(None),
        )
        .with_for_update()
        .all()
    )
    return movements, cities, queue_rows, adventures


def _shift_world_clocks(db: Session, world: models.World, pause_seconds: float) -> None:
    if pause_seconds <= 0:
        return
    from datetime import timedelta

    delta = timedelta(seconds=pause_seconds)
    movements, cities, queue_rows, adventures = _lock_world_clock_rows(db, world)

    for item in movements:
        item.arrival_time = item.arrival_time + delta
    for city in cities:
        if city.last_production is not None:
            city.last_production = city.last_production + delta
    for row in queue_rows:
        row.finish_time = row.finish_time + delta
    for adv in adventures:
        adv.started_at = adv.started_at + delta


def status_of(world: models.World) -> str:
    status = getattr(world, "lifecycle_status", None)
    if status in WORLD_STATES:
        # During the BM-0072 compatibility window, disagreement with the
        # legacy flag fails closed instead of making an inactive legacy world
        # playable. Lifecycle transitions always keep both fields aligned.
        if status == "open" and world.is_active is False:
            return "closed" if world.ended_at is not None else "paused"
        return str(status)
    if world.is_active:
        return "open"
    return "closed" if world.ended_at is not None else "paused"


def transition_world(
    db: Session,
    world_id: int,
    *,
    target_status: str,
    expected_status: str | None = None,
    reason: str,
    admin_user: models.User,
) -> models.World:
    normalized_reason = (reason or "").strip()
    if not normalized_reason:
        raise HTTPException(status_code=400, detail="Lifecycle transition reason is required")
    if target_status not in WORLD_STATES:
        raise HTTPException(status_code=400, detail="Unknown world lifecycle status")

    try:
        world = (
            db.query(models.World)
            .filter(models.World.id == world_id)
            .with_for_update()
            .populate_existing()
            .one_or_none()
        )
        if world is None:
            raise HTTPException(status_code=404, detail="World not found")

        current = status_of(world)
        if expected_status is not None and current != expected_status:
            raise HTTPException(
                status_code=409,
                detail=f"Stale world lifecycle state: expected {expected_status}, found {current}",
            )
        if current == target_status:
            return world
        if target_status not in ALLOWED_TRANSITIONS[current]:
            raise HTTPException(
                status_code=409,
                detail=f"Invalid world lifecycle transition: {current} -> {target_status}",
            )

        now = utc_now()
        if target_status == "paused":
            # Establish a hard pause barrier. If a worker already owns one of
            # these rows, this transition waits for it to finish before the
            # paused state can commit. Record the effective pause timestamp
            # only after the barrier has been acquired so pre-commit wait time
            # is never counted as paused gameplay time.
            _lock_world_clock_rows(db, world)
            now = utc_now()
            world.pause_started_at = now
        elif target_status == "open":
            pause_started_at = _aware(world.pause_started_at)
            if current == "paused" and pause_started_at is not None:
                pause_seconds = max((now - pause_started_at).total_seconds(), 0.0)
                _shift_world_clocks(db, world, pause_seconds)
            world.pause_started_at = None
        elif target_status == "closed":
            if world.ended_at is None:
                world.ended_at = now
            world.pause_started_at = None

        world.lifecycle_status = target_status
        world.lifecycle_changed_at = now
        world.is_active = target_status == "open"

        admin_service.log_action(
            db,
            admin_user.id,
            "world_lifecycle_transition",
            {
                "world_id": world.id,
                "from_status": current,
                "to_status": target_status,
                "reason": normalized_reason,
            },
        )
        db.add(world)
        db.commit()
        db.refresh(world)
        return world
    except Exception:
        db.rollback()
        raise

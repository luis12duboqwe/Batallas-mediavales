"""Server-authoritative BM-0072 world lifecycle transitions."""

from __future__ import annotations

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


def status_of(world: models.World) -> str:
    status = getattr(world, "lifecycle_status", None)
    if status in WORLD_STATES:
        return str(status)
    if world.is_active:
        return "open"
    return "closed" if world.ended_at is not None else "paused"


def transition_world(
    db: Session,
    world_id: int,
    *,
    target_status: str,
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
        if current == target_status:
            return world
        if target_status not in ALLOWED_TRANSITIONS[current]:
            raise HTTPException(
                status_code=409,
                detail=f"Invalid world lifecycle transition: {current} -> {target_status}",
            )

        now = utc_now()
        if target_status == "paused":
            world.pause_started_at = now
        elif target_status == "open":
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

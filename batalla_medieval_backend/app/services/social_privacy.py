from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models


def _require_world_member(db: Session, user_id: int, world_id: int) -> None:
    exists = (
        db.query(models.PlayerWorld.id)
        .filter(
            models.PlayerWorld.user_id == user_id,
            models.PlayerWorld.world_id == world_id,
        )
        .first()
    )
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Player is not a member of this world",
        )


def interaction_blocked(
    db: Session,
    user_a_id: int,
    user_b_id: int,
    world_id: int,
) -> bool:
    """Return true when either player blocks the other in this world."""

    if int(user_a_id) == int(user_b_id):
        return False
    return (
        db.query(models.UserBlock.id)
        .filter(
            models.UserBlock.world_id == world_id,
            or_(
                (
                    (models.UserBlock.blocker_id == user_a_id)
                    & (models.UserBlock.blocked_id == user_b_id)
                ),
                (
                    (models.UserBlock.blocker_id == user_b_id)
                    & (models.UserBlock.blocked_id == user_a_id)
                ),
            ),
        )
        .first()
        is not None
    )


def block_user(
    db: Session,
    blocker_id: int,
    blocked_id: int,
    world_id: int,
) -> models.UserBlock:
    if int(blocker_id) == int(blocked_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot block yourself",
        )

    try:
        # Serialize a user's privacy writes and verify durable world membership.
        db.query(models.User).filter(models.User.id == blocker_id).with_for_update().one()
        _require_world_member(db, blocker_id, world_id)
        _require_world_member(db, blocked_id, world_id)

        existing = (
            db.query(models.UserBlock)
            .filter(
                models.UserBlock.blocker_id == blocker_id,
                models.UserBlock.blocked_id == blocked_id,
                models.UserBlock.world_id == world_id,
            )
            .one_or_none()
        )
        if existing is not None:
            db.commit()
            db.refresh(existing)
            return existing

        row = models.UserBlock(
            blocker_id=blocker_id,
            blocked_id=blocked_id,
            world_id=world_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        db.rollback()
        raise


def unblock_user(
    db: Session,
    blocker_id: int,
    blocked_id: int,
    world_id: int,
) -> None:
    try:
        db.query(models.User).filter(models.User.id == blocker_id).with_for_update().one()
        row = (
            db.query(models.UserBlock)
            .filter(
                models.UserBlock.blocker_id == blocker_id,
                models.UserBlock.blocked_id == blocked_id,
                models.UserBlock.world_id == world_id,
            )
            .with_for_update()
            .one_or_none()
        )
        if row is not None:
            db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        raise


def list_blocks(db: Session, blocker_id: int, world_id: int) -> list[models.UserBlock]:
    _require_world_member(db, blocker_id, world_id)
    return (
        db.query(models.UserBlock)
        .filter(
            models.UserBlock.blocker_id == blocker_id,
            models.UserBlock.world_id == world_id,
        )
        .order_by(models.UserBlock.created_at.asc(), models.UserBlock.id.asc())
        .all()
    )

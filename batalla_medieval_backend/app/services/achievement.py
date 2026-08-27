from typing import Iterable, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models


def _lock_world_membership(db: Session, user_id: int, world_id: int) -> models.PlayerWorld:
    """Serialize medal mutations for one player/world on PostgreSQL."""

    membership = (
        db.query(models.PlayerWorld)
        .filter(
            models.PlayerWorld.user_id == user_id,
            models.PlayerWorld.world_id == world_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if membership is None:
        raise ValueError("Honor medal progress requires membership in the target world")
    return membership


def _ensure_progress_entries(
    db: Session,
    user_id: int,
    world_id: int,
    achievements: Iterable[models.Achievement],
    *,
    commit: bool = True,
) -> List[models.AchievementProgress]:
    achievement_ids = [achievement.id for achievement in achievements]
    if not achievement_ids:
        return []

    existing_progress = (
        db.query(models.AchievementProgress)
        .filter(
            models.AchievementProgress.user_id == user_id,
            models.AchievementProgress.world_id == world_id,
            models.AchievementProgress.achievement_id.in_(achievement_ids),
        )
        .with_for_update()
        .all()
    )
    progress_by_id = {progress.achievement_id: progress for progress in existing_progress}

    created = []
    for achievement_id in achievement_ids:
        if achievement_id not in progress_by_id:
            progress = models.AchievementProgress(
                user_id=user_id,
                achievement_id=achievement_id,
                world_id=world_id,
                current_progress=0,
                status="pending",
            )
            db.add(progress)
            created.append(progress)
            progress_by_id[achievement_id] = progress
    if created:
        db.flush()
    if commit:
        db.commit()
        for progress in created:
            db.refresh(progress)
    return [progress_by_id[aid] for aid in achievement_ids]


def _resolve_unambiguous_world(db: Session, user_id: int) -> int:
    world_ids = [
        int(row[0])
        for row in (
            db.query(models.PlayerWorld.world_id)
            .filter(models.PlayerWorld.user_id == user_id)
            .distinct()
            .order_by(models.PlayerWorld.world_id.asc())
            .all()
        )
    ]
    if len(world_ids) != 1:
        raise ValueError("Honor medal progress requires an explicit world_id")
    return world_ids[0]


def get_user_achievements(
    db: Session,
    user: models.User,
    world_id: int,
) -> list[tuple[models.Achievement, models.AchievementProgress]]:
    achievements = db.query(models.Achievement).order_by(models.Achievement.id.asc()).all()
    if not achievements:
        return []
    # Creating missing display rows is also a write; serialize it against event
    # updates so a first UI read cannot race a medal-producing event.
    _lock_world_membership(db, user.id, world_id)
    progress_entries = _ensure_progress_entries(db, user.id, world_id, achievements)
    return list(zip(achievements, progress_entries))


def update_achievement_progress(
    db: Session,
    user_id: int,
    *args,
    world_id: int | None = None,
    increment: int | float | None = None,
    absolute_value: int | float | None = None,
) -> None:
    """Update honor progress atomically inside exactly one world."""

    if len(args) == 2:
        if world_id is not None:
            raise TypeError("world_id supplied twice")
        resolved_world_id = int(args[0])
        requirement_type = str(args[1])
    elif len(args) == 1:
        resolved_world_id = int(world_id) if world_id is not None else _resolve_unambiguous_world(db, user_id)
        requirement_type = str(args[0])
    else:
        raise TypeError("update_achievement_progress requires requirement_type and world context")

    achievements = (
        db.query(models.Achievement)
        .filter(models.Achievement.requirement_type == requirement_type)
        .order_by(models.Achievement.id.asc())
        .all()
    )
    if not achievements:
        return

    # PlayerWorld is unique for (user, world), giving every medal mutation for
    # that scope one stable lock before rows are read/created. This prevents both
    # duplicate first inserts and lost increments under concurrent domain events.
    _lock_world_membership(db, user_id, resolved_world_id)
    progress_entries = _ensure_progress_entries(
        db,
        user_id,
        resolved_world_id,
        achievements,
        commit=False,
    )

    for achievement, progress in zip(achievements, progress_entries):
        new_progress = int(progress.current_progress or 0)
        if absolute_value is not None:
            new_progress = max(new_progress, int(absolute_value))
        if increment is not None:
            new_progress += int(increment)
        new_progress = min(new_progress, int(achievement.requirement_value))
        progress.current_progress = new_progress
        if progress.status != "claimed" and progress.current_progress >= achievement.requirement_value:
            progress.status = "completed"
        db.add(progress)
    db.commit()


def claim_achievement(
    db: Session,
    user: models.User,
    world_id: int,
    achievement_id: int,
) -> models.AchievementProgress:
    """Record an earned honor medal without granting gameplay advantages."""

    achievement = db.query(models.Achievement).filter(models.Achievement.id == achievement_id).first()
    if not achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Honor medal not found")

    _lock_world_membership(db, user.id, world_id)
    progress = (
        db.query(models.AchievementProgress)
        .filter(
            models.AchievementProgress.achievement_id == achievement_id,
            models.AchievementProgress.user_id == user.id,
            models.AchievementProgress.world_id == world_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if not progress or progress.status != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Honor medal not ready to claim")

    progress.status = "claimed"
    db.add(progress)
    db.add(
        models.Log(
            user_id=user.id,
            action="claim_honor_medal",
            details=(
                f"Claimed honor medal {achievement.title} in world {world_id}; "
                "no resources, troops, production, speed or combat bonus granted"
            ),
        )
    )
    db.commit()
    db.refresh(progress)
    return progress

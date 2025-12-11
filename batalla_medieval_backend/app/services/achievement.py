from typing import Iterable, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .. import models


def _ensure_progress_entries(
    db: Session, user_id: int, achievements: Iterable[models.Achievement]
) -> List[models.AchievementProgress]:
    achievement_ids = [achievement.id for achievement in achievements]
    existing_progress = (
        db.query(models.AchievementProgress)
        .filter(
            models.AchievementProgress.user_id == user_id,
            models.AchievementProgress.achievement_id.in_(achievement_ids),
        )
        .all()
    )
    progress_by_id = {progress.achievement_id: progress for progress in existing_progress}

    created = []
    for achievement_id in achievement_ids:
        if achievement_id not in progress_by_id:
            progress = models.AchievementProgress(
                user_id=user_id,
                achievement_id=achievement_id,
                current_progress=0,
                status="pending",
            )
            db.add(progress)
            created.append(progress)
            progress_by_id[achievement_id] = progress
    if created:
        db.commit()
        for progress in created:
            db.refresh(progress)
    return [progress_by_id[aid] for aid in achievement_ids]


def get_user_achievements(db: Session, user: models.User) -> list[tuple[models.Achievement, models.AchievementProgress]]:
    achievements = db.query(models.Achievement).all()
    if not achievements:
        return []
    progress_entries = _ensure_progress_entries(db, user.id, achievements)
    return list(zip(achievements, progress_entries))


def update_achievement_progress(
    db: Session,
    user_id: int,
    requirement_type: str,
    *,
    increment: int | float | None = None,
    absolute_value: int | float | None = None,
) -> None:
    achievements = (
        db.query(models.Achievement)
        .filter(models.Achievement.requirement_type == requirement_type)
        .all()
    )
    if not achievements:
        return
    progress_entries = _ensure_progress_entries(db, user_id, achievements)

    for achievement, progress in zip(achievements, progress_entries):
        new_progress = progress.current_progress
        if absolute_value is not None:
            new_progress = max(new_progress, int(absolute_value))
        if increment is not None:
            new_progress += int(increment)
        new_progress = min(new_progress, achievement.requirement_value)
        progress.current_progress = new_progress
        if progress.status != "claimed" and progress.current_progress >= achievement.requirement_value:
            progress.status = "completed"
        db.add(progress)
    db.commit()


def claim_achievement(db: Session, user: models.User, achievement_id: int) -> models.AchievementProgress:
    achievement = db.query(models.Achievement).filter(models.Achievement.id == achievement_id).first()
    if not achievement:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Achievement not found")

    progress = (
        db.query(models.AchievementProgress)
        .filter(
            models.AchievementProgress.achievement_id == achievement_id,
            models.AchievementProgress.user_id == user.id,
        )
        .first()
    )
    if not progress or progress.status != "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Achievement not ready to claim")

    progress.status = "claimed"
    db.add(progress)

    log_entry = models.Log(
        user_id=user.id,
        action="claim_achievement",
        details=f"Claimed achievement {achievement.title} and received {achievement.reward_value} {achievement.reward_type}",
    )
    db.add(log_entry)
    db.commit()
    db.refresh(progress)
    return progress

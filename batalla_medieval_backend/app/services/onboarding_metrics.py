"""Privacy-safe aggregate onboarding metrics for G4 product observability."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now

TUTORIAL_FINAL_STEP = 7


def _step_histogram(db: Session, *, inactive_before=None) -> dict[str, int]:
    query = db.query(models.User.tutorial_step, func.count(models.User.id)).filter(
        models.User.is_admin.is_(False)
    )
    if inactive_before is not None:
        query = query.filter(
            models.User.tutorial_reward_claimed.is_(False),
            models.User.last_active_at < inactive_before,
        )

    rows = query.group_by(models.User.tutorial_step).all()
    histogram = {str(step): 0 for step in range(TUTORIAL_FINAL_STEP + 1)}
    for raw_step, count in rows:
        step = max(0, min(int(raw_step or 0), TUTORIAL_FINAL_STEP))
        histogram[str(step)] += int(count)
    return histogram


def get_onboarding_metrics(db: Session, *, window_hours: int = 24) -> dict:
    """Return onboarding/abandonment aggregates without player identifiers."""

    if window_hours < 1:
        raise ValueError("window_hours must be positive")

    cutoff = utc_now() - timedelta(hours=window_hours)
    player_filter = models.User.is_admin.is_(False)

    total_players = int(
        db.query(func.count(models.User.id)).filter(player_filter).scalar() or 0
    )
    joined_world = int(
        db.query(func.count(distinct(models.PlayerWorld.user_id)))
        .join(models.User, models.User.id == models.PlayerWorld.user_id)
        .filter(player_filter)
        .scalar()
        or 0
    )
    completed = int(
        db.query(func.count(models.User.id))
        .filter(player_filter, models.User.tutorial_reward_claimed.is_(True))
        .scalar()
        or 0
    )
    active_window = int(
        db.query(func.count(models.User.id))
        .filter(player_filter, models.User.last_active_at >= cutoff)
        .scalar()
        or 0
    )
    inactive_incomplete = int(
        db.query(func.count(models.User.id))
        .filter(
            player_filter,
            models.User.tutorial_reward_claimed.is_(False),
            models.User.last_active_at < cutoff,
        )
        .scalar()
        or 0
    )

    step_counts = _step_histogram(db)
    inactive_by_step = _step_histogram(db, inactive_before=cutoff)
    reached_step = {
        str(step): sum(
            count for key, count in step_counts.items() if int(key) >= step
        )
        for step in range(TUTORIAL_FINAL_STEP + 1)
    }

    completion_rate = (completed / total_players) if total_players else 0.0
    join_rate = (joined_world / total_players) if total_players else 0.0

    return {
        "window_hours": int(window_hours),
        "total_players": total_players,
        "joined_world": joined_world,
        "tutorial_completed": completed,
        "active_in_window": active_window,
        "inactive_incomplete": inactive_incomplete,
        "join_rate": join_rate,
        "completion_rate": completion_rate,
        "tutorial_step_counts": step_counts,
        "reached_step_counts": reached_step,
        "inactive_incomplete_by_step": inactive_by_step,
    }

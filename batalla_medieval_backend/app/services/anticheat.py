from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now


RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
    "movement.create": (12, 10),
    "market.offer.create": (20, 10),
    "market.npc_trade": (20, 10),
    "market.offer.accept": (20, 10),
    "market.offer.cancel": (20, 10),
    "market.transport": (20, 10),
}
_RATE_BUCKET_RETRIES = 4
_DEFAULT_DEDUPE_SECONDS = 5


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLAlchemy datetimes before comparing them to aware UTC now."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def flag_violation(
    db: Session,
    user: models.User,
    violation_type: str,
    severity: str,
    details: str,
    reviewer_id: int | None = None,
    *,
    commit: bool = True,
    dedupe_seconds: int = _DEFAULT_DEDUPE_SECONDS,
) -> models.AntiCheatFlag:
    """Persist evidence only; heuristics never sanction a player directly."""

    user_id = int(user.id)
    now = utc_now()
    if dedupe_seconds > 0:
        cutoff = now - timedelta(seconds=int(dedupe_seconds))
        existing = (
            db.query(models.AntiCheatFlag)
            .filter(
                models.AntiCheatFlag.user_id == user_id,
                models.AntiCheatFlag.type_of_violation == violation_type,
                models.AntiCheatFlag.severity == severity,
                models.AntiCheatFlag.details == details,
                models.AntiCheatFlag.resolved_status == "pending",
                models.AntiCheatFlag.timestamp >= cutoff,
            )
            .order_by(models.AntiCheatFlag.timestamp.desc(), models.AntiCheatFlag.id.desc())
            .first()
        )
        if existing is not None:
            return existing

    flag = models.AntiCheatFlag(
        user_id=user_id,
        type_of_violation=violation_type,
        severity=severity,
        details=details,
        reviewer_id=reviewer_id,
        reviewed_by_admin=False,
        resolved_status="pending",
        timestamp=now,
    )
    db.add(flag)
    if commit:
        db.commit()
        db.refresh(flag)
    else:
        db.flush()
    return flag


def log_action(db: Session, user: models.User, action: str, details: str) -> models.Log:
    log = models.Log(user_id=user.id, action=action, details=details)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _lock_or_create_rate_bucket(
    db: Session,
    *,
    user_id: int,
    action_key: str,
    now: datetime,
) -> models.AntiCheatRateBucket:
    for _ in range(_RATE_BUCKET_RETRIES):
        bucket = (
            db.query(models.AntiCheatRateBucket)
            .filter(
                models.AntiCheatRateBucket.user_id == user_id,
                models.AntiCheatRateBucket.action_key == action_key,
            )
            .with_for_update()
            .one_or_none()
        )
        if bucket is not None:
            return bucket

        bucket = models.AntiCheatRateBucket(
            user_id=user_id,
            action_key=action_key,
            window_started_at=now,
            request_count=0,
            updated_at=now,
        )
        db.add(bucket)
        try:
            db.flush()
            return bucket
        except IntegrityError:
            db.rollback()

    raise RuntimeError("Could not serialize anti-cheat rate bucket")


def enforce_action_rate_limit(
    db: Session,
    user: models.User,
    action_key: str,
    *,
    limit: int | None = None,
    window_seconds: int | None = None,
) -> None:
    """Enforce one durable user/action window and never apply a sanction.

    The bucket row is locked on PostgreSQL. A concurrent first-use insert is
    retried after the unique constraint resolves, preventing two workers from
    both treating the same action as the first request in the window.
    """

    configured = RATE_LIMIT_RULES.get(action_key)
    if configured is None and (limit is None or window_seconds is None):
        raise ValueError(f"Unknown rate-limited action: {action_key}")
    configured_limit, configured_window = configured or (limit, window_seconds)
    resolved_limit = int(limit if limit is not None else configured_limit)
    resolved_window = int(
        window_seconds if window_seconds is not None else configured_window
    )
    if resolved_limit <= 0 or resolved_window <= 0:
        raise ValueError("Rate-limit values must be positive")

    user_id = int(user.id)
    now = utc_now()
    bucket = _lock_or_create_rate_bucket(
        db,
        user_id=user_id,
        action_key=action_key,
        now=now,
    )

    window_started = _as_utc(bucket.window_started_at)
    window_end = window_started + timedelta(seconds=resolved_window)
    if now >= window_end:
        bucket.window_started_at = now
        bucket.request_count = 0
        bucket.blocked_until = None
        window_started = now
        window_end = now + timedelta(seconds=resolved_window)

    blocked_until = (
        _as_utc(bucket.blocked_until) if bucket.blocked_until is not None else None
    )
    if blocked_until is not None and now < blocked_until:
        retry_after = max(1, math.ceil((blocked_until - now).total_seconds()))
        flag_violation(
            db,
            user,
            f"rate_limit:{action_key}",
            "high",
            f"Rate limit exceeded for {action_key}",
            commit=False,
            dedupe_seconds=resolved_window,
        )
        bucket.updated_at = now
        db.add(bucket)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    if int(bucket.request_count or 0) >= resolved_limit:
        bucket.blocked_until = window_end
        bucket.updated_at = now
        flag_violation(
            db,
            user,
            f"rate_limit:{action_key}",
            "high",
            f"Rate limit exceeded for {action_key}",
            commit=False,
            dedupe_seconds=resolved_window,
        )
        db.add(bucket)
        db.commit()
        retry_after = max(1, math.ceil((window_end - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    bucket.request_count = int(bucket.request_count or 0) + 1
    bucket.updated_at = now
    db.add(bucket)
    db.commit()


def check_action_speed(db: Session, user: models.User, action_name: str):
    """Legacy heuristic signal; authoritative blocking uses rate buckets."""

    now = utc_now()
    if user.last_action_at:
        delta = (now - _as_utc(user.last_action_at)).total_seconds()
        if delta < 0.1:
            flag_violation(
                db,
                user,
                "bot_detection",
                "critical",
                f"Actions executed too quickly ({delta * 1000:.1f}ms) during {action_name}",
            )
    user.last_action_at = now
    db.add(user)
    db.commit()


def check_repeated_actions(db: Session, user: models.User, signature: str):
    recent_logs = (
        db.query(models.Log)
        .filter(models.Log.user_id == user.id, models.Log.action == signature)
        .order_by(models.Log.timestamp.desc())
        .limit(5)
        .all()
    )
    if len(recent_logs) >= 4:
        newest = _as_utc(recent_logs[0].timestamp)
        oldest = _as_utc(recent_logs[-1].timestamp)
        if (newest - oldest) <= timedelta(seconds=5):
            flag_violation(
                db,
                user,
                "bot_detection",
                "high",
                f"Detected repeating pattern for action {signature} ({len(recent_logs)}x in 5s)",
            )


def check_multiaccount_ip(db: Session, user: models.User, client_ip: str | None):
    if not client_ip:
        return
    other_users = (
        db.query(models.User)
        .filter(models.User.last_login_ip == client_ip, models.User.id != user.id)
        .all()
    )
    if other_users:
        flag_violation(
            db,
            user,
            "multiaccount_ip",
            "high",
            f"IP {client_ip} also used by {[u.username for u in other_users]}",
        )
    user.last_login_ip = client_ip
    user.last_login_at = utc_now()
    db.add(user)
    db.commit()


def check_repeated_account_interactions(
    db: Session, origin_city: models.City, target_city: models.City, movement_type: str
):
    if origin_city.owner is None or target_city.owner is None:
        return

    recent = (
        db.query(models.Movement)
        .filter(
            models.Movement.origin_city_id == origin_city.id,
            models.Movement.target_city_id == target_city.id,
            models.Movement.movement_type == movement_type,
        )
        .order_by(models.Movement.created_at.desc())
        .limit(5)
        .all()
    )
    if len(recent) >= 4:
        timestamps = [_as_utc(mv.arrival_time) for mv in recent if mv.arrival_time]
        if len(timestamps) >= 2:
            intervals = [
                abs((timestamps[i] - timestamps[i + 1]).total_seconds())
                for i in range(len(timestamps) - 1)
            ]
            if intervals and max(intervals) - min(intervals) < 1:
                flag_violation(
                    db,
                    origin_city.owner,
                    "multiaccount_actions",
                    "high",
                    f"Repeated identical {movement_type} actions between "
                    f"{origin_city.owner.username} and {target_city.owner.username}",
                )


def check_movement_legitimacy(
    db: Session,
    origin_city: models.City,
    target_city: models.City,
    movement_type: str,
    arrival_time,
    speed_used: float,
    spy_count: int = 0,
):
    if origin_city.owner is None:
        return

    now = utc_now()
    arrival_utc = _as_utc(arrival_time)
    distance = ((origin_city.x - target_city.x) ** 2 + (origin_city.y - target_city.y) ** 2) ** 0.5
    min_hours = distance / max(speed_used, 0.01)
    actual_hours = max(0.0, (arrival_utc - now).total_seconds() / 3600)
    if actual_hours + 0.01 < min_hours:
        flag_violation(
            db,
            origin_city.owner,
            "fake_attack",
            "critical",
            f"Arrival time {arrival_utc} too fast for distance {distance:.2f} at speed {speed_used}",
        )

    total_troops = sum(troop.quantity for troop in origin_city.troops)
    if total_troops > origin_city.population_max:
        flag_violation(
            db,
            origin_city.owner,
            "fake_attack",
            "high",
            f"Troop count {total_troops} exceeds population {origin_city.population_max}",
        )

    check_repeated_account_interactions(db, origin_city, target_city, movement_type)

    signature = f"movement:{movement_type}:{origin_city.id}->{target_city.id}"
    log_action(db, origin_city.owner, signature, f"Scheduled arrival at {arrival_utc}")
    check_repeated_actions(db, origin_city.owner, signature)

    if movement_type == "spy" and spy_count <= 0:
        flag_violation(
            db,
            origin_city.owner,
            "spy_exploit",
            "medium",
            "Invalid spy count provided",
        )


def check_spy_result(db: Session, attacker: models.User, success_chance: float, success: bool):
    details = f"success_chance={success_chance:.3f};success={success}"
    log_action(db, attacker, "spy_result", details)
    if success and success_chance < 0.1:
        lucky_reports = (
            db.query(models.Log)
            .filter(
                models.Log.user_id == attacker.id,
                models.Log.action == "spy_result",
                models.Log.details.like("success_chance=0.__%;success=True"),
            )
            .order_by(models.Log.timestamp.desc())
            .limit(3)
            .all()
        )
        if len(lucky_reports) >= 3:
            flag_violation(
                db,
                attacker,
                "spy_exploit",
                "high",
                "Repeated spy successes with <10% chance detected",
            )

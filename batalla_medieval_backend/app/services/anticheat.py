from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now


def _persist(db: Session, *instances: object):
    for instance in instances:
        if instance is not None:
            db.add(instance)
    db.commit()


def flag_violation(
    db: Session,
    user: models.User,
    violation_type: str,
    severity: str,
    details: str,
    reviewer_id: int | None = None,
) -> models.AntiCheatFlag:
    flag = models.AntiCheatFlag(
        user_id=user.id,
        type_of_violation=violation_type,
        severity=severity,
        details=details,
        reviewer_id=reviewer_id,
    )

    if severity.lower() == "critical":
        user.is_frozen = True
        user.freeze_reason = details
        log_action(db, user, "account_freeze", f"Frozen due to {violation_type}: {details}")

    _persist(db, flag, user)
    db.refresh(flag)
    return flag


def log_action(db: Session, user: models.User, action: str, details: str) -> models.Log:
    log = models.Log(user_id=user.id, action=action, details=details)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def check_action_speed(db: Session, user: models.User, action_name: str):
    now = utc_now()
    if user.last_action_at:
        delta = (now - user.last_action_at).total_seconds()
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
        newest = recent_logs[0].timestamp
        oldest = recent_logs[-1].timestamp
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
        timestamps = [mv.arrival_time for mv in recent if mv.arrival_time]
        if len(timestamps) >= 2:
            intervals = [
                abs((timestamps[i] - timestamps[i + 1]).total_seconds()) for i in range(len(timestamps) - 1)
            ]
            if intervals and max(intervals) - min(intervals) < 1:
                flag_violation(
                    db,
                    origin_city.owner,
                    "multiaccount_actions",
                    "high",
                    f"Repeated identical {movement_type} actions between {origin_city.owner.username} and {target_city.owner.username}",
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
    now = utc_now()
    distance = ((origin_city.x - target_city.x) ** 2 + (origin_city.y - target_city.y) ** 2) ** 0.5
    min_hours = distance / max(speed_used, 0.01)
    actual_hours = max(0.0, (arrival_time - now).total_seconds() / 3600)
    if actual_hours + 0.01 < min_hours:
        flag_violation(
            db,
            origin_city.owner,
            "fake_attack",
            "critical",
            f"Arrival time {arrival_time} too fast for distance {distance:.2f} at speed {speed_used}",
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
    log_action(db, origin_city.owner, signature, f"Scheduled arrival at {arrival_time}")
    check_repeated_actions(db, origin_city.owner, signature)

    if spy_count and movement_type == "spy" and spy_count <= 0:
        flag_violation(db, origin_city.owner, "spy_exploit", "medium", "Invalid spy count provided")


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

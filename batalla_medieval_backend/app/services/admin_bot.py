import json
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now


WELCOME_MESSAGE_SUBJECT = "Welcome to Batalla Medieval!"
TIP_MESSAGE_SUBJECT = "Hacienda Upgrade Tip"
ANTI_CHEAT_WARNING_SUBJECT = "Automatic Anti-Cheat Warning"


def _log_action(
    db: Session,
    action: str,
    details: Dict,
    user_id: Optional[int] = None,
) -> models.AdminBotLog:
    entry = models.AdminBotLog(
        action=action,
        user_id=user_id,
        details=json.dumps(details, sort_keys=True),
    )
    db.add(entry)
    return entry


def _old_notification_count(db: Session, retention_days: int = 30) -> int:
    cutoff = utc_now() - timedelta(days=retention_days)
    return int(
        db.query(func.count(models.Message.id))
        .filter(
            models.Message.timestamp < cutoff,
            models.Message.subject.in_([WELCOME_MESSAGE_SUBJECT, TIP_MESSAGE_SUBJECT, ANTI_CHEAT_WARNING_SUBJECT]),
        )
        .scalar()
        or 0
    )


def _old_log_counts(db: Session, retention_days: int = 90) -> tuple[int, int]:
    cutoff = utc_now() - timedelta(days=retention_days)
    admin_bot_logs = int(
        db.query(func.count(models.AdminBotLog.id))
        .filter(models.AdminBotLog.timestamp < cutoff)
        .scalar()
        or 0
    )
    audit_logs = int(
        db.query(func.count(models.Log.id))
        .filter(models.Log.timestamp < cutoff)
        .scalar()
        or 0
    )
    return admin_bot_logs, audit_logs


def _inactive_player_count(db: Session, inactivity_days: int = 30) -> int:
    cutoff = utc_now() - timedelta(days=inactivity_days)
    return int(
        db.query(func.count(models.User.id))
        .filter(
            models.User.is_admin.is_(False),
            models.User.username != "AdminBot",
            models.User.last_active_at < cutoff,
        )
        .scalar()
        or 0
    )


def _empty_alliance_count(db: Session) -> int:
    rows = (
        db.query(models.Alliance.id)
        .outerjoin(models.AllianceMember)
        .group_by(models.Alliance.id)
        .having(func.count(models.AllianceMember.id) == 0)
        .all()
    )
    return len(rows)


def _unreviewed_anticheat_count(db: Session) -> int:
    return int(
        db.query(func.count(models.AntiCheatFlag.id))
        .filter(models.AntiCheatFlag.reviewed_by_admin.is_(False))
        .scalar()
        or 0
    )


def run_admin_bot(db: Session) -> List[str]:
    """Return operational diagnostics without mutating player or audit state.

    BM-0073 deliberately disables the legacy maintenance bot's destructive
    behaviour. Retention, account deletion and automated sanctions require
    dedicated reviewed policies; until then this endpoint is report-only.
    The only write performed here is an AdminBotLog describing aggregate
    diagnostics for operators.
    """

    old_notifications = _old_notification_count(db)
    old_admin_logs, old_audit_logs = _old_log_counts(db)
    inactive_players = _inactive_player_count(db)
    empty_alliances = _empty_alliance_count(db)
    unreviewed_flags = _unreviewed_anticheat_count(db)

    diagnostics = {
        "mode": "report_only",
        "old_automated_notifications": old_notifications,
        "old_admin_bot_logs": old_admin_logs,
        "old_audit_logs": old_audit_logs,
        "inactive_players": inactive_players,
        "empty_alliances": empty_alliances,
        "unreviewed_anticheat_flags": unreviewed_flags,
    }
    _log_action(db, "report_only_run", diagnostics)
    db.flush()

    return [
        f"Report-only: {old_notifications} old automated notifications detected",
        f"Report-only: {old_admin_logs} old admin-bot logs and {old_audit_logs} old audit logs detected",
        f"Report-only: {inactive_players} inactive players detected",
        f"Report-only: {empty_alliances} empty alliances detected",
        f"Report-only: {unreviewed_flags} anti-cheat flags await review",
    ]

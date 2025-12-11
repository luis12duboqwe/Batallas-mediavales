import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models


WELCOME_MESSAGE_SUBJECT = "Welcome to Batalla Medieval!"
WELCOME_MESSAGE_BODY = "Welcome to Batalla Medieval!"
TIP_MESSAGE_SUBJECT = "Hacienda Upgrade Tip"
TIP_MESSAGE_BODY = "Remember to upgrade your Hacienda to support more troops."
ANTI_CHEAT_WARNING_SUBJECT = "Automatic Anti-Cheat Warning"
SEVERE_FLAG_SEVERITIES = {"high", "severe"}


def _ensure_admin_bot_user(db: Session) -> models.User:
    bot_user = db.query(models.User).filter(models.User.username == "AdminBot").first()
    if bot_user:
        return bot_user

    bot_user = models.User(
        username="AdminBot",
        email="adminbot@batallamedieval.local",
        hashed_password="!",
        is_admin=True,
        last_active_at=datetime.utcnow(),
        is_frozen=False,
    )
    db.add(bot_user)
    db.commit()
    db.refresh(bot_user)
    return bot_user


def _log_action(db: Session, action: str, details: Dict, user_id: Optional[int] = None) -> models.AdminBotLog:
    entry = models.AdminBotLog(action=action, user_id=user_id, details=json.dumps(details))
    db.add(entry)
    return entry


def _remove_old_notifications(db: Session, bot_user: models.User, retention_days: int = 30) -> str:
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    deleted = (
        db.query(models.Message)
        .filter(models.Message.sender_id == bot_user.id, models.Message.timestamp < cutoff)
        .delete()
    )
    _log_action(
        db,
        "cleanup_notifications",
        {"deleted": deleted, "cutoff": cutoff.isoformat()},
    )
    return f"Removed {deleted} old notifications"


def _delete_old_logs(db: Session, retention_days: int = 90) -> str:
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    deleted_admin_logs = (
        db.query(models.AdminBotLog)
        .filter(models.AdminBotLog.timestamp < cutoff)
        .delete()
    )
    deleted_user_logs = db.query(models.Log).filter(models.Log.timestamp < cutoff).delete()
    _log_action(
        db,
        "cleanup_logs",
        {
            "admin_bot_logs_deleted": deleted_admin_logs,
            "user_logs_deleted": deleted_user_logs,
            "cutoff": cutoff.isoformat(),
        },
    )
    return f"Deleted {deleted_admin_logs} admin bot logs and {deleted_user_logs} user logs"


def _clear_inactive_players(db: Session, inactivity_days: int = 30) -> str:
    cutoff = datetime.utcnow() - timedelta(days=inactivity_days)
    inactive_users = (
        db.query(models.User)
        .filter(
            models.User.is_admin.is_(False),
            models.User.username != "AdminBot",
            models.User.last_active_at < cutoff,
        )
        .all()
    )
    removed_ids: List[int] = []
    for user in inactive_users:
        removed_ids.append(user.id)
        db.delete(user)
    _log_action(
        db,
        "cleanup_inactive_players",
        {"removed_user_ids": removed_ids, "cutoff": cutoff.isoformat()},
    )
    return f"Removed {len(removed_ids)} inactive players"


def _delete_empty_alliances(db: Session) -> str:
    empty_alliances = (
        db.query(models.Alliance)
        .outerjoin(models.AllianceMember)
        .group_by(models.Alliance.id)
        .having(func.count(models.AllianceMember.id) == 0)
        .all()
    )
    deleted_ids: List[int] = []
    for alliance in empty_alliances:
        deleted_ids.append(alliance.id)
        db.delete(alliance)
    _log_action(db, "cleanup_empty_alliances", {"deleted_alliance_ids": deleted_ids})
    return f"Deleted {len(deleted_ids)} empty alliances"


def _message_exists(db: Session, sender_id: int, receiver_id: int, subject: str) -> bool:
    return (
        db.query(models.Message)
        .filter(
            models.Message.sender_id == sender_id,
            models.Message.receiver_id == receiver_id,
            models.Message.subject == subject,
        )
        .first()
        is not None
    )


def _send_auto_messages(db: Session, bot_user: models.User) -> str:
    new_users = (
        db.query(models.User)
        .filter(
            models.User.is_admin.is_(False),
            models.User.username != bot_user.username,
            models.User.created_at >= datetime.utcnow() - timedelta(days=1),
        )
        .all()
    )
    sent_count = 0
    for user in new_users:
        if not _message_exists(db, bot_user.id, user.id, WELCOME_MESSAGE_SUBJECT):
            db.add(
                models.Message(
                    sender_id=bot_user.id,
                    receiver_id=user.id,
                    subject=WELCOME_MESSAGE_SUBJECT,
                    content=WELCOME_MESSAGE_BODY,
                )
            )
            sent_count += 1
        if not _message_exists(db, bot_user.id, user.id, TIP_MESSAGE_SUBJECT):
            db.add(
                models.Message(
                    sender_id=bot_user.id,
                    receiver_id=user.id,
                    subject=TIP_MESSAGE_SUBJECT,
                    content=TIP_MESSAGE_BODY,
                )
            )
            sent_count += 1
    _log_action(
        db,
        "send_auto_messages",
        {"sent_messages": sent_count, "target_user_ids": [user.id for user in new_users]},
    )
    return f"Sent {sent_count} onboarding messages"


def _processed_flag_keys(db: Session) -> set[tuple[int, int]]:
    processed = set()
    audit_logs = (
        db.query(models.AdminBotLog)
        .filter(models.AdminBotLog.action.in_(["anti_cheat_warning", "anti_cheat_freeze"]))
        .all()
    )
    for log in audit_logs:
        try:
            details = json.loads(log.details)
            key = (details.get("flagged_user_id"), details.get("source_log_id"))
            if key[0] is not None and key[1] is not None:
                processed.add(key)
        except (TypeError, json.JSONDecodeError):
            continue
    return processed


def _handle_anti_cheat_flags(db: Session, bot_user: models.User) -> str:
    processed_keys = _processed_flag_keys(db)
    flagged_logs = db.query(models.Log).filter(models.Log.action == "anti_cheat_flag").all()
    warnings_sent = 0
    freezes_applied = 0
    for flag_log in flagged_logs:
        try:
            details = json.loads(flag_log.details)
        except (TypeError, json.JSONDecodeError):
            details = {}
        flagged_user_id = details.get("flagged_user_id") or details.get("user_id")
        severity = str(details.get("severity", "low")).lower()
        reason = details.get("reason", "Suspicious activity detected.")
        if flagged_user_id is None:
            continue
        key = (flagged_user_id, flag_log.id)
        if key in processed_keys:
            continue

        user = db.query(models.User).filter(models.User.id == flagged_user_id).first()
        if not user:
            _log_action(
                db,
                "anti_cheat_flag_missing_user",
                {"flagged_user_id": flagged_user_id, "source_log_id": flag_log.id},
            )
            continue

        warning_message = models.Message(
            sender_id=bot_user.id,
            receiver_id=user.id,
            subject=ANTI_CHEAT_WARNING_SUBJECT,
            content=f"{reason} Please adhere to the game rules.",
        )
        db.add(warning_message)
        warnings_sent += 1
        _log_action(
            db,
            "anti_cheat_warning",
            {
                "flagged_user_id": flagged_user_id,
                "source_log_id": flag_log.id,
                "severity": severity,
            },
            user_id=flagged_user_id,
        )

        if severity in SEVERE_FLAG_SEVERITIES:
            user.is_frozen = True
            freezes_applied += 1
            _log_action(
                db,
                "anti_cheat_freeze",
                {
                    "flagged_user_id": flagged_user_id,
                    "source_log_id": flag_log.id,
                    "severity": severity,
                    "action": "account_frozen_pending_review",
                },
                user_id=flagged_user_id,
            )
    return f"Processed {warnings_sent} warnings and {freezes_applied} freezes"


def run_admin_bot(db: Session) -> List[str]:
    bot_user = _ensure_admin_bot_user(db)
    actions_taken: List[str] = []

    actions_taken.append(_remove_old_notifications(db, bot_user))
    actions_taken.append(_delete_old_logs(db))
    actions_taken.append(_clear_inactive_players(db))
    actions_taken.append(_delete_empty_alliances(db))
    actions_taken.append(_send_auto_messages(db, bot_user))
    actions_taken.append(_handle_anti_cheat_flags(db, bot_user))

    db.commit()
    return actions_taken

from __future__ import annotations

from typing import Iterable
import asyncio
import logging

from sqlalchemy.orm import Session
from asgiref.sync import async_to_sync

from .. import models
from . import emailer, socket_manager

logger = logging.getLogger(__name__)

EMAIL_NOTIFICATION_TYPES = {"attack_incoming", "building_complete", "event_started"}


def create_notification(
    db: Session,
    user: models.User,
    title: str,
    body: str,
    *,
    notification_type: str = "message_received",
    allow_email: bool = True,
) -> models.Notification:
    """Persist and dispatch one notification.

    ``title`` and ``body`` remain positional-or-keyword for compatibility with
    older domain services. Newer callers should still pass the semantic
    ``notification_type`` explicitly; message notifications use the safe
    default when a legacy caller omits it.
    """

    notification = models.Notification(
        user_id=user.id,
        title=title,
        body=body,
        type=notification_type,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    try:
        payload = {
            "id": notification.id,
            "title": notification.title,
            "body": notification.body,
            "type": notification.type,
            "created_at": notification.created_at.isoformat(),
            "read": notification.read,
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(socket_manager.notify_user(user.id, "notification", payload))
        except RuntimeError:
            asyncio.run(socket_manager.notify_user(user.id, "notification", payload))
    except Exception as exc:
        logger.error("Failed to send websocket notification: %s", exc)

    if allow_email and user.email_notifications and notification_type in EMAIL_NOTIFICATION_TYPES:
        emailer.send_email(user.email, title, body)

    return notification


def list_notifications(db: Session, user: models.User) -> list[models.Notification]:
    return (
        db.query(models.Notification)
        .filter(models.Notification.user_id == user.id)
        .order_by(models.Notification.created_at.desc())
        .all()
    )


def mark_as_read(
    db: Session, user: models.User, notification_id: int
) -> models.Notification | None:
    notification = (
        db.query(models.Notification)
        .filter(
            models.Notification.id == notification_id, models.Notification.user_id == user.id
        )
        .first()
    )
    if notification and not notification.read:
        notification.read = True
        db.add(notification)
        db.commit()
        db.refresh(notification)
    return notification


def notify_global_event(db: Session, users: Iterable[models.User], event_name: str) -> None:
    for user in users:
        create_notification(
            db,
            user,
            title="Evento global iniciado",
            body=f"El evento '{event_name}' ha comenzado en tu mundo.",
            notification_type="event_started",
        )


def notify_event_started(db: Session, event_name: str) -> None:
    users = db.query(models.User).all()
    notify_global_event(db, users, event_name)

from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from .. import models
from . import emailer

EMAIL_NOTIFICATION_TYPES = {"attack_incoming", "building_complete", "event_started"}


def create_notification(
    db: Session,
    user: models.User,
    *,
    title: str,
    body: str,
    notification_type: str,
    allow_email: bool = True,
) -> models.Notification:
    notification = models.Notification(
        user_id=user.id,
        title=title,
        body=body,
        type=notification_type,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

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

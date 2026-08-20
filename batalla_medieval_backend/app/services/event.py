from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Session

from .. import models, schemas
from ..utils import utc_now
from . import balance

# Compatibility aliases. Event balance data lives only in ``balance``.
DEFAULT_MODIFIERS = balance.EVENT_DEFAULT_MODIFIERS
EVENT_TEMPLATES = balance.EVENT_TEMPLATES


def _merge_modifiers(custom: Dict[str, float] | None) -> Dict[str, float]:
    merged = DEFAULT_MODIFIERS.copy()
    if custom:
        merged.update({k: float(v) for k, v in custom.items() if v is not None})
    return merged


def get_active_event(db: Session, world_id: int = 1) -> models.WorldEvent | None:
    now = utc_now()
    return (
        db.query(models.WorldEvent)
        .filter(
            models.WorldEvent.world_id == world_id,
            models.WorldEvent.start_time <= now,
            models.WorldEvent.end_time >= now,
        )
        .order_by(models.WorldEvent.start_time.desc())
        .first()
    )


def get_active_modifiers(db: Session, world_id: int = 1) -> Dict[str, float]:
    event = get_active_event(db, world_id=world_id)
    if not event:
        return DEFAULT_MODIFIERS.copy()
    return _merge_modifiers(event.get_modifiers())


def create_event(db: Session, payload: schemas.EventCreate) -> models.WorldEvent:
    template = EVENT_TEMPLATES.get(payload.event_type.upper())
    if not template:
        raise ValueError("Unknown event type")

    name, description, template_modifiers = template
    event = models.WorldEvent(
        world_id=payload.world_id,
        name=name,
        description=description,
        start_time=payload.start_time,
        end_time=payload.end_time,
        modifiers=_merge_modifiers(template_modifiers),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
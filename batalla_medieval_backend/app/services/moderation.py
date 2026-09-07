"""Global reversible content moderation for BM-0073."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import admin as admin_service


def _snapshot(target) -> dict:
    return {
        "is_hidden": bool(target.is_hidden),
        "moderation_reason": target.moderation_reason,
        "moderated_by_id": target.moderated_by_id,
        "moderated_at": target.moderated_at.isoformat() if target.moderated_at else None,
    }


def _apply_snapshot(target, state: dict) -> None:
    target.is_hidden = bool(state["is_hidden"])
    target.moderation_reason = state.get("moderation_reason")
    target.moderated_by_id = state.get("moderated_by_id")
    raw_time = state.get("moderated_at")
    target.moderated_at = datetime.fromisoformat(raw_time) if raw_time else None


def _target_for_update(db: Session, kind: str, target_id: int):
    if kind == "chat_message":
        model = models.ChatMessage
    elif kind == "forum_post":
        model = models.ForumPost
    else:
        raise HTTPException(status_code=400, detail="Unsupported moderation target")
    target = db.query(model).filter(model.id == target_id).with_for_update().one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Moderation target not found")
    return target


def get_target(db: Session, kind: str, target_id: int):
    if kind == "chat_message":
        target = db.query(models.ChatMessage).filter(models.ChatMessage.id == target_id).one_or_none()
    elif kind == "forum_post":
        target = db.query(models.ForumPost).filter(models.ForumPost.id == target_id).one_or_none()
    else:
        raise HTTPException(status_code=400, detail="Unsupported moderation target")
    if target is None:
        raise HTTPException(status_code=404, detail="Moderation target not found")
    return target


def set_hidden(
    db: Session,
    *,
    kind: str,
    target_id: int,
    hidden: bool,
    reason: str,
    admin_user: models.User,
    support_case_id: int | None = None,
) -> models.Log:
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise HTTPException(status_code=400, detail="Moderation reason is required")
    admin_service._validate_support_case(db, support_case_id)
    target = _target_for_update(db, kind, target_id)
    before = _snapshot(target)
    target.is_hidden = bool(hidden)
    target.moderation_reason = normalized_reason
    target.moderated_by_id = admin_user.id
    target.moderated_at = utc_now()
    after = _snapshot(target)
    action = "moderate_chat_message" if kind == "chat_message" else "moderate_forum_post"
    log = admin_service.log_action(
        db,
        admin_user.id,
        action,
        {"hidden": bool(hidden)},
        target_type=kind,
        target_id=target_id,
        reason=normalized_reason,
        before_state=before,
        after_state=after,
        reversible=before != after,
        support_case_id=support_case_id,
    )
    db.commit()
    db.refresh(log)
    return log


def revert_from_audit(db: Session, original: models.Log, before: dict, after: dict) -> None:
    if original.action == "moderate_chat_message":
        kind = "chat_message"
    elif original.action == "moderate_forum_post":
        kind = "forum_post"
    else:
        raise HTTPException(status_code=409, detail="Unsupported moderation reversal")
    target = _target_for_update(db, kind, int(original.target_id))
    current = _snapshot(target)
    if current != after:
        raise HTTPException(status_code=409, detail="Target changed after the audited action")
    _apply_snapshot(target, before)

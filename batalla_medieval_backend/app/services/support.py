"""BM-0073 support-case domain service."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import admin as admin_service
from . import admin_permissions
from . import world_membership

VALID_STATUSES = {"open", "in_progress", "resolved", "closed"}
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
ALLOWED_TRANSITIONS = {
    "open": {"in_progress", "resolved"},
    "in_progress": {"open", "resolved"},
    "resolved": {"in_progress", "closed"},
    "closed": set(),
}


def create_case(
    db: Session,
    requester: models.User,
    *,
    subject: str,
    description: str,
    world_id: int | None,
) -> models.SupportCase:
    if world_id is not None:
        try:
            world_membership.require_world_membership(
                db,
                user_id=requester.id,
                world_id=world_id,
            )
        except world_membership.WorldAccessDeniedError as exc:
            raise HTTPException(status_code=403, detail="You have not joined this world") from exc

    case = models.SupportCase(
        requester_id=requester.id,
        world_id=world_id,
        subject=subject.strip(),
        description=description.strip(),
        status="open",
        priority="normal",
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def list_requester_cases(db: Session, requester_id: int) -> list[models.SupportCase]:
    return (
        db.query(models.SupportCase)
        .filter(models.SupportCase.requester_id == requester_id)
        .order_by(models.SupportCase.created_at.desc(), models.SupportCase.id.desc())
        .all()
    )


def get_requester_case(db: Session, requester_id: int, case_id: int) -> models.SupportCase:
    case = (
        db.query(models.SupportCase)
        .filter(
            models.SupportCase.id == case_id,
            models.SupportCase.requester_id == requester_id,
        )
        .one_or_none()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Support case not found")
    return case


def list_admin_cases(
    db: Session,
    *,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 100,
) -> list[models.SupportCase]:
    query = db.query(models.SupportCase)
    if status is not None:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid support status")
        query = query.filter(models.SupportCase.status == status)
    if priority is not None:
        if priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid support priority")
        query = query.filter(models.SupportCase.priority == priority)
    return (
        query.order_by(models.SupportCase.updated_at.desc(), models.SupportCase.id.desc())
        .limit(limit)
        .all()
    )


def update_case(
    db: Session,
    case_id: int,
    *,
    admin_user: models.User,
    reason: str,
    status: str | None = None,
    priority: str | None = None,
    assigned_to_id: int | None = None,
    resolution: str | None = None,
) -> models.SupportCase:
    case = (
        db.query(models.SupportCase)
        .filter(models.SupportCase.id == case_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Support case not found")

    normalized_reason = reason.strip()
    if not normalized_reason:
        raise HTTPException(status_code=400, detail="Administrative reason is required")

    before = {
        "status": case.status,
        "priority": case.priority,
        "assigned_to_id": case.assigned_to_id,
        "resolution": case.resolution,
    }

    if status is not None and status != case.status:
        if status not in ALLOWED_TRANSITIONS.get(case.status, set()):
            raise HTTPException(
                status_code=409,
                detail=f"Invalid support transition: {case.status} -> {status}",
            )
        case.status = status
        now = utc_now()
        if status == "resolved":
            if not (resolution or case.resolution or "").strip():
                raise HTTPException(status_code=400, detail="Resolution is required")
            case.resolved_at = now
            case.closed_at = None
        elif status == "closed":
            case.closed_at = now
        elif status == "in_progress":
            case.closed_at = None

    if priority is not None:
        if priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid support priority")
        case.priority = priority

    if assigned_to_id is not None:
        assignee = db.query(models.User).filter(models.User.id == assigned_to_id).one_or_none()
        if assignee is None or not admin_permissions.effective_admin_role(assignee):
            raise HTTPException(status_code=400, detail="Assignee must be an administrator")
        case.assigned_to_id = assigned_to_id

    if resolution is not None:
        case.resolution = resolution.strip() or None

    after = {
        "status": case.status,
        "priority": case.priority,
        "assigned_to_id": case.assigned_to_id,
        "resolution": case.resolution,
    }
    admin_service.log_action(
        db,
        admin_user.id,
        "support_case_update",
        {"case_id": case.id},
        target_type="support_case",
        target_id=case.id,
        reason=normalized_reason,
        before_state=before,
        after_state=after,
        reversible=False,
        support_case_id=case.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case

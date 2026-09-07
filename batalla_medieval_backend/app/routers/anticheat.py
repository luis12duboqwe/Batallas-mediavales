from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import anticheat as anticheat_schema
from ..services import admin as admin_service
from ..services import admin_permissions
from ..utils import utc_now

router = APIRouter(prefix="/anticheat", tags=["anticheat"])


@router.get("/flags", response_model=list[anticheat_schema.AntiCheatFlagRead])
def list_flags(
    user_id: int | None = None,
    severity: str | None = None,
    resolved_status: str | None = None,
    violation_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        admin_permissions.require_capability("audit.read")
    ),
):
    query = db.query(models.AntiCheatFlag)
    if user_id is not None:
        query = query.filter(models.AntiCheatFlag.user_id == user_id)
    if severity is not None:
        query = query.filter(models.AntiCheatFlag.severity == severity)
    if resolved_status is not None:
        query = query.filter(models.AntiCheatFlag.resolved_status == resolved_status)
    if violation_type is not None:
        query = query.filter(models.AntiCheatFlag.type_of_violation == violation_type)
    return query.order_by(models.AntiCheatFlag.timestamp.desc(), models.AntiCheatFlag.id.desc()).limit(limit).all()


@router.patch("/resolve/{flag_id}", response_model=anticheat_schema.AntiCheatFlagRead)
def resolve_flag(
    flag_id: int,
    payload: anticheat_schema.AntiCheatResolveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        admin_permissions.require_capability("admin.manage")
    ),
    reason: str = Depends(admin_permissions.require_reason),
):
    flag = (
        db.query(models.AntiCheatFlag)
        .filter(models.AntiCheatFlag.id == flag_id)
        .with_for_update()
        .one_or_none()
    )
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")

    before = {
        "resolved_status": flag.resolved_status,
        "reviewed_by_admin": bool(flag.reviewed_by_admin),
        "reviewer_id": flag.reviewer_id,
        "reviewed_at": flag.reviewed_at.isoformat() if flag.reviewed_at else None,
        "resolution_reason": flag.resolution_reason,
    }
    reviewed_at = utc_now()
    flag.resolved_status = payload.resolved_status
    flag.reviewed_by_admin = True
    flag.reviewer_id = current_user.id
    flag.reviewed_at = reviewed_at
    flag.resolution_reason = reason
    after = {
        "resolved_status": flag.resolved_status,
        "reviewed_by_admin": True,
        "reviewer_id": flag.reviewer_id,
        "reviewed_at": reviewed_at.isoformat(),
        "resolution_reason": flag.resolution_reason,
    }
    admin_service.log_action(
        db,
        current_user.id,
        "resolve_anticheat_flag",
        {"target_user_id": flag.user_id},
        target_type="anticheat_flag",
        target_id=flag.id,
        reason=reason,
        before_state=before,
        after_state=after,
        reversible=False,
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return flag

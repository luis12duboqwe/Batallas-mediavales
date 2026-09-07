from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import anticheat as anticheat_schema
from ..services import admin as admin_service
from ..services import admin_permissions

router = APIRouter(prefix="/anticheat", tags=["anticheat"])


@router.get("/flags", response_model=list[anticheat_schema.AntiCheatFlagRead])
def list_flags(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        admin_permissions.require_capability("audit.read")
    ),
):
    return (
        db.query(models.AntiCheatFlag)
        .order_by(models.AntiCheatFlag.timestamp.desc())
        .all()
    )


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
    }
    flag.resolved_status = payload.resolved_status
    flag.reviewed_by_admin = payload.reviewed_by_admin
    flag.reviewer_id = current_user.id
    after = {
        "resolved_status": flag.resolved_status,
        "reviewed_by_admin": bool(flag.reviewed_by_admin),
        "reviewer_id": flag.reviewer_id,
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

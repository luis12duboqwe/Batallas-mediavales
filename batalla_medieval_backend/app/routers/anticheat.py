from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..routers.auth import get_current_user
from ..schemas import anticheat as anticheat_schema

router = APIRouter(prefix="/anticheat", tags=["anticheat"])


@router.get("/flags", response_model=list[anticheat_schema.AntiCheatFlagRead])
def list_flags(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
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
    current_user: models.User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    flag = db.query(models.AntiCheatFlag).filter(models.AntiCheatFlag.id == flag_id).first()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    flag.resolved_status = payload.resolved_status
    flag.reviewed_by_admin = payload.reviewed_by_admin
    flag.reviewer_id = current_user.id
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return flag

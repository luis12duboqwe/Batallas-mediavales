from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import admin_bot as admin_bot_service

router = APIRouter(prefix="/admin_bot", tags=["admin_bot"])


def require_admin(current_user: models.User = Depends(get_current_user)):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


@router.post("/run", response_model=schemas.AdminBotRunResponse)
async def run_admin_bot_endpoint(
    db: Session = Depends(get_db), current_admin: models.User = Depends(require_admin)
):
    actions = admin_bot_service.run_admin_bot(db)
    return schemas.AdminBotRunResponse(detail="Admin bot executed", actions=actions)


@router.get("/logs", response_model=list[schemas.AdminBotLogRead])
async def get_admin_bot_logs(
    db: Session = Depends(get_db), current_admin: models.User = Depends(require_admin)
):
    logs = db.query(models.AdminBotLog).order_by(models.AdminBotLog.timestamp.desc()).all()
    return logs

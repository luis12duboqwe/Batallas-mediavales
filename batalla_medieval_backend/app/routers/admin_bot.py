from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import admin_bot as admin_bot_service
from ..services import admin_permissions

router = APIRouter(prefix="/admin_bot", tags=["admin_bot"])


@router.post("/run", response_model=schemas.AdminBotRunResponse)
async def run_admin_bot_endpoint(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("admin.manage")
    ),
):
    actions = admin_bot_service.run_admin_bot(db)
    return schemas.AdminBotRunResponse(detail="Admin bot executed", actions=actions)


@router.get("/logs", response_model=list[schemas.AdminBotLogRead])
async def get_admin_bot_logs(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("audit.read")
    ),
):
    logs = db.query(models.AdminBotLog).order_by(models.AdminBotLog.timestamp.desc()).all()
    return logs

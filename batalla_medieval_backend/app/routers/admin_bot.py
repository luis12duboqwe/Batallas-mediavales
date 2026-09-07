from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import admin as admin_service
from ..services import admin_bot as admin_bot_service
from ..services import admin_permissions

router = APIRouter(prefix="/admin_bot", tags=["admin_bot"])


@router.post("/run", response_model=schemas.AdminBotRunResponse)
async def run_admin_bot_endpoint(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("admin.manage")
    ),
    reason: str = Depends(admin_permissions.require_reason),
):
    actions = admin_bot_service.run_admin_bot(db)
    admin_service.log_action(
        db,
        current_admin.id,
        "run_admin_bot_report",
        {"action_count": len(actions)},
        target_type="admin_bot",
        target_id=None,
        reason=reason,
        before_state=None,
        after_state={"mode": "report_only", "actions": actions},
        reversible=False,
    )
    db.commit()
    return schemas.AdminBotRunResponse(detail="Admin bot report generated", actions=actions)


@router.get("/logs", response_model=list[schemas.AdminBotLogRead])
async def get_admin_bot_logs(
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("audit.read")
    ),
):
    logs = db.query(models.AdminBotLog).order_by(models.AdminBotLog.timestamp.desc()).all()
    return logs

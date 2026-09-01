from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import admin_permissions, support as support_service

router = APIRouter(prefix="/support", tags=["Support"])


@router.post("/cases", response_model=schemas.SupportCaseRead)
def create_support_case(
    payload: schemas.SupportCaseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return support_service.create_case(
        db,
        current_user,
        subject=payload.subject,
        description=payload.description,
        world_id=payload.world_id,
    )


@router.get("/cases", response_model=list[schemas.SupportCaseRead])
def list_my_support_cases(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return support_service.list_requester_cases(db, current_user.id)


@router.get("/cases/{case_id}", response_model=schemas.SupportCaseRead)
def get_my_support_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return support_service.get_requester_case(db, current_user.id, case_id)


@router.get("/admin/cases", response_model=list[schemas.SupportCaseRead])
def list_support_cases(
    status: str | None = None,
    priority: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("support.manage")
    ),
):
    return support_service.list_admin_cases(
        db,
        status=status,
        priority=priority,
        limit=limit,
    )


@router.patch("/admin/cases/{case_id}", response_model=schemas.SupportCaseRead)
def update_support_case(
    case_id: int,
    payload: schemas.SupportCaseAdminUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("support.manage")
    ),
):
    return support_service.update_case(
        db,
        case_id,
        admin_user=current_admin,
        **payload.model_dump(),
    )

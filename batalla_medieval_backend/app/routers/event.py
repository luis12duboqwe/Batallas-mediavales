from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import admin_permissions
from ..services import event as event_service

router = APIRouter(tags=["events"])


@router.get("/active", response_model=schemas.ActiveEventResponse)
def get_active_event(db: Session = Depends(get_db)):
    event = event_service.get_active_event(db)
    modifiers = event_service.get_active_modifiers(db)
    return schemas.ActiveEventResponse(event=event, modifiers=schemas.EventModifiers(**modifiers))


@router.post("/create", response_model=schemas.EventRead)
def create_event(
    payload: schemas.EventCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("admin.manage")
    ),
):
    try:
        event = event_service.create_event(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return event

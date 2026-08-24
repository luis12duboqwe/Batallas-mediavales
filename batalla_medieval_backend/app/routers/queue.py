from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..routers.responses import error_response
from ..services import queue as queue_service
from ..services import research as research_service

router = APIRouter(prefix="/queue", tags=["queues"])


@router.get("/status", response_model=schemas.QueueStatus)
def queue_status(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    queue_service.process_all_queues(db)
    queues = queue_service.get_active_queues_for_user(db, current_user, world_id=world_id)
    return schemas.QueueStatus(**queues)


@router.get("/building", response_model=list[schemas.BuildingQueueRead])
def list_building_queue(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    queues = queue_service.get_active_queues_for_user(db, current_user, world_id=world_id)
    return queues["building_queues"]


@router.get("/research", response_model=list[schemas.ResearchQueueRead])
def list_research_queue(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    queues = queue_service.get_active_queues_for_user(db, current_user, world_id=world_id)
    return queues["research_queues"]


@router.delete("/research/{queue_id}", status_code=204)
def cancel_research_queue(
    queue_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        success = research_service.cancel_research_queue(db, queue_id, current_user.id)
    except ValueError as exc:
        raise error_response(409, "queue_not_cancellable", str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="Queue entry not found or not owned by user")
    return None


@router.get("/troop", response_model=list[schemas.TroopQueueRead])
def list_troop_queue(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    queues = queue_service.get_active_queues_for_user(db, current_user, world_id=world_id)
    return queues["troop_queues"]

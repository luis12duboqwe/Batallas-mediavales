from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import queue as queue_service

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


@router.get("/troop", response_model=list[schemas.TroopQueueRead])
def list_troop_queue(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    queues = queue_service.get_active_queues_for_user(db, current_user, world_id=world_id)
    return queues["troop_queues"]

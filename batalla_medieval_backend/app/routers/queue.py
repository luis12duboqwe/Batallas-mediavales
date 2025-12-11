from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import queue as queue_service

router = APIRouter(prefix="/queue", tags=["queues"])


@router.get("/status", response_model=schemas.QueueStatus)
def queue_status(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    queue_service.process_all_queues(db)
    queues = queue_service.get_active_queues_for_user(db, current_user)
    return schemas.QueueStatus(**queues)

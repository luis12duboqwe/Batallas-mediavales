from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import queue as queue_service, troops

router = APIRouter(prefix="/troop", tags=["troops"])


@router.post("/train", response_model=schemas.TroopQueueRead)
def train_troops(
    payload: schemas.TroopQueueCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = db.query(models.City).filter(models.City.id == payload.city_id, models.City.owner_id == current_user.id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    queue_service.process_all_queues(db)
    try:
        troop_queue = troops.queue_training(db, city, payload.troop_type, payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return troop_queue

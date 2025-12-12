from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import queue as queue_service, troops

router = APIRouter(tags=["troops"])


@router.post("/train", response_model=schemas.TroopQueueRead)
def train_troops(
    payload: schemas.TroopQueueCreate,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = (
        db.query(models.City)
        .filter(
            models.City.id == payload.city_id,
            models.City.owner_id == current_user.id,
            models.City.world_id == world_id,
        )
        .first()
    )
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    queue_service.process_all_queues(db)
    try:
        troop_queue = troops.queue_training(db, city, payload.troop_type, payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return troop_queue


@router.delete("/queue/{queue_id}", status_code=204)
def cancel_queue(
    queue_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Cancel a troop training queue."""
    success = troops.cancel_troop_queue(db, queue_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Queue entry not found or not owned by user")
    return None


@router.post("/research")
def research_unit(
    payload: schemas.ResearchRequest,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = (
        db.query(models.City)
        .filter(
            models.City.id == payload.city_id,
            models.City.owner_id == current_user.id,
            models.City.world_id == world_id,
        )
        .first()
    )
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    try:
        troops.research_unit(db, city, payload.unit_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Unit researched"}

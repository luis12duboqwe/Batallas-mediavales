from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import movement

router = APIRouter(prefix="/movements", tags=["movements"])


@router.post("/", response_model=schemas.MovementRead)
def create_movement(
    payload: schemas.MovementCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    origin_city = (
        db.query(models.City)
        .filter(models.City.id == payload.origin_city_id, models.City.owner_id == current_user.id)
        .first()
    )
    if not origin_city:
        raise HTTPException(status_code=404, detail="Origin city not found")
    movement_obj = movement.send_movement(
        db, origin_city, payload.target_city_id, payload.movement_type, payload.troops_payload
    )
    return movement_obj


@router.get("/", response_model=list[schemas.MovementRead])
def list_movements(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    movements = (
        db.query(models.Movement)
        .join(models.City, models.Movement.origin_city_id == models.City.id)
        .filter(models.City.owner_id == current_user.id)
        .all()
    )
    return movements


@router.post("/process", response_model=list[schemas.MovementRead])
def process_movements(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    movement.process_arrived_movements(db)
    updated_movements = (
        db.query(models.Movement)
        .join(models.City, models.Movement.origin_city_id == models.City.id)
        .filter(models.City.owner_id == current_user.id)
        .all()
    )
    return updated_movements

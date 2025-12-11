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
    try:
        movement_obj = movement.send_movement(
            db,
            origin_city,
            payload.target_city_id,
            payload.movement_type,
            spy_count=payload.spy_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return movement_obj


@router.get("/", response_model=list[schemas.MovementRead])
def list_movements(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    movement.resolve_due_movements(db)
    movements = (
        db.query(models.Movement)
        .join(models.City, models.Movement.origin_city_id == models.City.id)
        .filter(models.City.owner_id == current_user.id)
        .all()
    )
    return movements


@router.post("/resolve", response_model=list[schemas.MovementRead])
def resolve_movements(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    user_cities = [city.id for city in current_user.cities]
    movements = movement.resolve_due_movements(db)
    filtered_movements = [mv for mv in movements if mv.origin_city_id in user_cities]
    return filtered_movements

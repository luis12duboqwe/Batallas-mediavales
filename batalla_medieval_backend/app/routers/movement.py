from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import movement, protection

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
    target_city = None
    if payload.movement_type == "attack":
        if protection.is_user_protected(current_user):
            raise HTTPException(status_code=400, detail="Protected players cannot launch attacks")
        target_city = db.query(models.City).filter(models.City.id == payload.target_city_id).first()
        if not target_city:
            raise HTTPException(status_code=404, detail="Target city not found")
        if protection.is_user_protected(target_city.owner):
            raise HTTPException(status_code=400, detail="Target city is under protection")
    try:
        movement_obj = movement.send_movement(
            db, origin_city, payload.target_city_id, payload.movement_type, target_city
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
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

from fastapi import APIRouter, Depends, HTTPException
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import movement, protection, queue as queue_service

router = APIRouter(prefix="/movements", tags=["movements"])


@router.post("/", response_model=schemas.MovementRead)
def create_movement(
    payload: schemas.MovementCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    origin_city = (
        db.query(models.City)
        .filter(
            models.City.id == payload.origin_city_id,
            models.City.owner_id == current_user.id,
            models.City.world_id == payload.world_id,
        )
        .first()
    )
    if not origin_city:
        raise HTTPException(status_code=404, detail="Origin city not found")
    target_city = None
    if payload.movement_type == "attack":
        if protection.is_user_protected(current_user):
            raise HTTPException(status_code=400, detail="Protected players cannot launch attacks")
        target_city = (
            db.query(models.City)
            .filter(models.City.id == payload.target_city_id, models.City.world_id == payload.world_id)
            .first()
        )
        if not target_city:
            raise HTTPException(status_code=404, detail="Target city not found")
        if protection.is_user_protected(target_city.owner):
            raise HTTPException(status_code=400, detail="Target city is under protection")
    try:
        movement_obj = movement.send_movement(
            db,
            origin_city,
            payload.target_city_id,
            payload.movement_type,
            target_city=target_city,
            spy_count=payload.spy_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    queue_service.process_all_queues(db)
    return movement_obj


@router.get("/", response_model=list[schemas.MovementRead])
def list_movements(
    world_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    queue_service.process_all_queues(db)
    movement.resolve_due_movements(db)
    movements = (
        db.query(models.Movement)
        .join(models.City, models.Movement.origin_city_id == models.City.id)
        .filter(models.City.owner_id == current_user.id, models.Movement.world_id == world_id)
        .all()
    )
    return movements


@router.post("/resolve", response_model=list[schemas.MovementRead])
def resolve_movements(
    world_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    user_cities = [city.id for city in current_user.cities]
    movements = movement.resolve_due_movements(db)
    filtered_movements = [mv for mv in movements if mv.origin_city_id in user_cities]
    return filtered_movements
@router.post("/process", response_model=list[schemas.MovementRead])
def process_movements(
    world_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    movement.process_arrived_movements(db)
    updated_movements = (
        db.query(models.Movement)
        .join(models.City, models.Movement.origin_city_id == models.City.id)
        .filter(models.City.owner_id == current_user.id, models.Movement.world_id == world_id)
        .all()
    )
    return updated_movements

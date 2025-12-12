"""Movement endpoints for creating and resolving marches."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..routers.responses import error_response
from ..services import movement, protection
from ..services import queue as queue_service

router = APIRouter(tags=["movements"])


@router.post("/", response_model=schemas.MovementRead)
def create_movement(
    payload: schemas.MovementCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a new movement for the requesting user's city."""

    origin_city = (
        db.query(models.City)
        .options(selectinload(models.City.owner), selectinload(models.City.world))
        .filter(
            models.City.id == payload.origin_city_id,
            models.City.owner_id == current_user.id,
            models.City.world_id == payload.world_id,
        )
        .first()
    )
    if not origin_city:
        raise error_response(404, "origin_not_found", "Origin city not found", {"city_id": payload.origin_city_id})

    target_city = None
    target_oasis = None
    
    if payload.target_city_id:
        if payload.movement_type == "attack":
            if protection.is_user_protected(current_user):
                raise error_response(400, "protection_active", "Protected players cannot launch attacks")
            target_city = (
                db.query(models.City)
                .options(selectinload(models.City.owner), selectinload(models.City.world))
                .filter(models.City.id == payload.target_city_id, models.City.world_id == payload.world_id)
                .first()
            )
            if not target_city:
                raise error_response(404, "target_not_found", "Target city not found", {"city_id": payload.target_city_id})
            if protection.is_user_protected(target_city.owner):
                raise error_response(400, "target_protected", "Target city is under protection")
    elif payload.target_oasis_id:
        target_oasis = (
            db.query(models.Oasis)
            .filter(models.Oasis.id == payload.target_oasis_id, models.Oasis.world_id == payload.world_id)
            .first()
        )
        if not target_oasis:
            raise error_response(404, "target_not_found", "Target oasis not found", {"oasis_id": payload.target_oasis_id})
    else:
        raise error_response(400, "invalid_target", "Must specify target_city_id or target_oasis_id")

    queue_service.process_all_queues(db)
    try:
        movement_obj = movement.send_movement(
            db,
            origin_city,
            payload.target_city_id,
            payload.movement_type,
            troops=payload.troops,
            spy_count=payload.spy_count,
            target_city=target_city,
            target_building=payload.target_building,
            target_oasis_id=payload.target_oasis_id
        )
    except ValueError as exc:
        raise error_response(400, "movement_creation_failed", str(exc)) from exc
    queue_service.process_all_queues(db)
    return movement_obj


@router.get("/", response_model=list[schemas.MovementRead])
def list_movements(
    world_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    """List all ongoing movements related to the current user (outgoing and incoming)."""

    queue_service.process_all_queues(db)
    movement.resolve_due_movements(db)
    
    user_city_ids = [city.id for city in current_user.cities]
    
    movements = (
        db.query(models.Movement)
        .filter(
            models.Movement.world_id == world_id,
            (models.Movement.origin_city_id.in_(user_city_ids)) | (models.Movement.target_city_id.in_(user_city_ids))
        )
        .all()
    )
    return movements


@router.post("/resolve", response_model=list[schemas.MovementRead])
def resolve_movements(
    world_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    """Resolve due spy movements and return those owned by the user."""

    user_cities = [city.id for city in current_user.cities]
    movements = movement.resolve_due_movements(db)
    filtered_movements = [mv for mv in movements if mv.origin_city_id in user_cities and mv.world_id == world_id]
    return filtered_movements


@router.post("/process", response_model=list[schemas.MovementRead])
def process_movements(
    world_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    """Process arrived movements and return updated records owned by the user."""

    movement.process_arrived_movements(db)
    updated_movements = (
        db.query(models.Movement)
        .join(models.City, models.Movement.origin_city_id == models.City.id)
        .filter(models.City.owner_id == current_user.id, models.Movement.world_id == world_id)
        .all()
    )
    return updated_movements

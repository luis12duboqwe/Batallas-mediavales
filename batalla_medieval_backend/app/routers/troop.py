from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..routers.responses import error_response
from ..schemas.troop import UnitAvailability
from ..services import production, troops, unit_catalog

router = APIRouter(tags=["troops"])


@router.get("/available", response_model=list[UnitAvailability])
def available_units(
    city_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Return the exact research/training catalog applicable to one city."""

    city = (
        db.query(models.City)
        .options(selectinload(models.City.buildings))
        .filter(
            models.City.id == city_id,
            models.City.owner_id == current_user.id,
            models.City.world_id == world_id,
        )
        .first()
    )
    if not city:
        raise error_response(404, "city_not_found", "City not found", {"city_id": city_id})

    production.recalculate_resources(db, city)
    db.expire(city, ["buildings"])
    return unit_catalog.get_availability(db, city)


@router.post("/train", response_model=schemas.TroopQueueRead)
def train_troops(
    payload: schemas.TroopQueueCreate,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = (
        db.query(models.City)
        .options(selectinload(models.City.owner))
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
        return troops.queue_training(db, city, payload.troop_type, payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/queue/{queue_id}", status_code=204)
def cancel_queue(
    queue_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Cancel a not-yet-completed troop training queue."""

    try:
        success = troops.cancel_troop_queue(db, queue_id, current_user.id)
    except ValueError as exc:
        raise error_response(409, "queue_not_cancellable", str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="Queue entry not found or not owned by user")
    return None


@router.post("/research", response_model=schemas.ResearchQueueRead, status_code=201)
def research_unit(
    payload: schemas.ResearchRequest,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Pay and queue research. The unit unlocks only after queue completion."""

    city = (
        db.query(models.City)
        .options(selectinload(models.City.buildings))
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
        return troops.research_unit(db, city, payload.unit_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

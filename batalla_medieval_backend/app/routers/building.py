"""Building endpoints for handling upgrades."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..routers.responses import error_response
from ..services import building, production, queue as queue_service

router = APIRouter(prefix="/building", tags=["buildings"])


@router.post("/upgrade", response_model=schemas.BuildingQueueRead)
def upgrade_building(
    payload: schemas.BuildingQueueCreate,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Queue a building upgrade for a city owned by the current user."""

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
        raise error_response(404, "city_not_found", "City not found", {"city_id": payload.city_id})
    queue_service.process_all_queues(db)
    production.recalculate_resources(db, city)
    try:
        building_queue = building.queue_upgrade(db, city, payload.building_type)
    except ValueError as exc:
        raise error_response(400, "upgrade_failed", str(exc)) from exc
    return building_queue

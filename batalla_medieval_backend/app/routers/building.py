from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import building, production, queue as queue_service

router = APIRouter(prefix="/building", tags=["buildings"])


@router.post("/upgrade", response_model=schemas.BuildingQueueRead)
def upgrade_building(
    payload: schemas.BuildingQueueCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = db.query(models.City).filter(models.City.id == payload.city_id, models.City.owner_id == current_user.id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    queue_service.process_all_queues(db)
    production.recalculate_resources(db, city)
    try:
        building_queue = building.queue_upgrade(db, city, payload.building_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return building_queue

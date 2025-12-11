from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import building, production

router = APIRouter(prefix="/buildings", tags=["buildings"])


@router.post("/{city_id}", response_model=schemas.BuildingRead)
def upgrade_building(
    city_id: int,
    payload: schemas.BuildingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = db.query(models.City).filter(models.City.id == city_id, models.City.owner_id == current_user.id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    production.recalculate_resources(db, city)
    building_model = building.queue_upgrade(db, city, payload.name)
    return building_model

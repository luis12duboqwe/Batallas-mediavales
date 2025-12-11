from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import troops

router = APIRouter(prefix="/troops", tags=["troops"])


@router.post("/{city_id}", response_model=schemas.TroopRead)
def train_troops(
    city_id: int,
    payload: schemas.TroopCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = db.query(models.City).filter(models.City.id == city_id, models.City.owner_id == current_user.id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    troop = troops.queue_training(db, city, payload.unit_type, payload.quantity)
    return troop

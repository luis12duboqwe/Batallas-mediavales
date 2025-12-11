from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import production, protection

router = APIRouter(prefix="/cities", tags=["cities"])


@router.post("/", response_model=schemas.CityRead)
def create_city(
    city: schemas.CityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_city = models.City(name=city.name, x=city.x, y=city.y, owner_id=current_user.id)
    db.add(db_city)
    db.commit()
    db.refresh(db_city)
    production.recalculate_resources(db, db_city)
    return db_city


@router.get("/", response_model=list[schemas.CityRead])
def list_cities(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    cities = db.query(models.City).filter(models.City.owner_id == current_user.id).all()
    for city in cities:
        production.recalculate_resources(db, city)
        city.is_protected = protection.is_user_protected(city.owner)
    return cities


@router.get("/{city_id}", response_model=schemas.CityRead)
def get_city(city_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    city = db.query(models.City).filter(models.City.id == city_id, models.City.owner_id == current_user.id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    production.recalculate_resources(db, city)
    city.is_protected = protection.is_user_protected(city.owner)
    return city

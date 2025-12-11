from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import admin as admin_service

router = APIRouter(prefix="/admin", tags=["admin"])


class ResourceUpdate(BaseModel):
    wood: float | None = None
    clay: float | None = None
    iron: float | None = None
    population_max: int | None = None


class BuildingLevelUpdate(BaseModel):
    new_level: int


class TroopUpdate(BaseModel):
    troops: Dict[str, int]


class AdminCityCreate(BaseModel):
    name: str
    owner_id: int
    x: int = 0
    y: int = 0
    wood: float = 500.0
    clay: float = 500.0
    iron: float = 500.0
    population_max: int = 100


class CoordinatesUpdate(BaseModel):
    x: int
    y: int


def require_admin(current_user: models.User = Depends(get_current_user)):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


@router.patch("/city/{city_id}/resources", response_model=schemas.CityRead)
def modify_city_resources(
    city_id: int,
    payload: ResourceUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    updates = payload.dict(exclude_unset=True)
    return admin_service.update_city_resources(db, city_id, updates, current_admin)


@router.patch("/city/{city_id}/building/{building_type}", response_model=schemas.BuildingRead)
def set_building_level(
    city_id: int,
    building_type: str,
    payload: BuildingLevelUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    return admin_service.set_building_level(db, city_id, building_type, payload.new_level, current_admin)


@router.patch("/city/{city_id}/troops", response_model=List[schemas.TroopRead])
def set_troop_amounts(
    city_id: int,
    payload: TroopUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    return admin_service.set_troop_amounts(db, city_id, payload.troops, current_admin)


@router.post("/city/create", response_model=schemas.CityRead)
def create_city(
    payload: AdminCityCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    return admin_service.create_city(db, payload.dict(), current_admin)


@router.patch("/city/{city_id}/coordinates", response_model=schemas.CityRead)
def teleport_city(
    city_id: int,
    payload: CoordinatesUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    return admin_service.teleport_city(db, city_id, payload.x, payload.y, current_admin)


@router.delete("/user/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    admin_service.delete_user(db, user_id, current_admin)
    return {"detail": "User deleted"}


@router.delete("/city/{city_id}")
def delete_city(
    city_id: int,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    admin_service.delete_city(db, city_id, current_admin)
    return {"detail": "City deleted"}

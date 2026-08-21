from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import admin as admin_service
from ..services import onboarding_metrics

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
    world_id: int
    x: int = 0
    y: int = 0
    wood: float = 500.0
    clay: float = 500.0
    iron: float = 500.0
    population_max: int = 100


class CoordinatesUpdate(BaseModel):
    x: int
    y: int


class UserFreezeUpdate(BaseModel):
    is_frozen: bool
    reason: str | None = None


class OnboardingMetricsRead(BaseModel):
    window_hours: int
    total_players: int
    joined_world: int
    tutorial_completed: int
    active_in_window: int
    inactive_incomplete: int
    join_rate: float
    completion_rate: float
    tutorial_step_counts: Dict[str, int]
    reached_step_counts: Dict[str, int]
    inactive_incomplete_by_step: Dict[str, int]


def require_admin(current_user: models.User = Depends(get_current_user)):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


@router.get("/metrics/onboarding", response_model=OnboardingMetricsRead)
def onboarding_product_metrics(
    window_hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """Return aggregate onboarding metrics without player identifiers or PII."""

    return onboarding_metrics.get_onboarding_metrics(
        db,
        window_hours=window_hours,
    )


@router.get("/logs", response_model=List[schemas.LogRead])
def list_admin_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    return admin_service.list_logs(db, limit=limit)


@router.patch("/user/{user_id}/freeze", response_model=schemas.UserRead)
def set_user_freeze(
    user_id: int,
    payload: UserFreezeUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    return admin_service.set_user_freeze(
        db,
        user_id,
        is_frozen=payload.is_frozen,
        reason=payload.reason,
        admin_user=current_admin,
    )


@router.patch("/city/{city_id}/resources", response_model=schemas.CityRead)
def modify_city_resources(
    city_id: int,
    payload: ResourceUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    updates = payload.model_dump(exclude_unset=True)
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
    return admin_service.create_city(db, payload.model_dump(), current_admin)


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

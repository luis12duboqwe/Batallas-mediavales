from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import admin as admin_service
from ..services import admin_permissions, balance, onboarding_metrics

router = APIRouter(prefix="/admin", tags=["admin"])


class ReasonedRequest(BaseModel):
    reason: str
    support_case_id: int | None = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Administrative reason is required")
        return normalized


class ResourceUpdate(ReasonedRequest):
    wood: float | None = None
    stone: float | None = None
    iron: float | None = None
    gold: float | None = None
    population_max: int | None = None


class BuildingLevelUpdate(ReasonedRequest):
    new_level: int


class TroopUpdate(ReasonedRequest):
    troops: Dict[str, int]


class AdminCityCreate(ReasonedRequest):
    name: str
    owner_id: int
    world_id: int
    x: int = 0
    y: int = 0
    wood: float = balance.CITY_STARTING_RESOURCES["wood"]
    stone: float = balance.CITY_STARTING_RESOURCES["stone"]
    iron: float = balance.CITY_STARTING_RESOURCES["iron"]
    gold: float = balance.CITY_STARTING_RESOURCES["gold"]
    population_max: int = 100


class CoordinatesUpdate(ReasonedRequest):
    x: int
    y: int


class UserFreezeUpdate(ReasonedRequest):
    is_frozen: bool


class AdminRoleUpdate(ReasonedRequest):
    role: str | None = None
    enabled: bool = True


class RevertRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Reversal reason is required")
        return normalized


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


@router.get("/metrics/onboarding", response_model=OnboardingMetricsRead)
def onboarding_product_metrics(
    window_hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("audit.read")
    ),
):
    return onboarding_metrics.get_onboarding_metrics(db, window_hours=window_hours)


@router.get("/logs", response_model=List[schemas.LogRead])
def list_admin_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("audit.read")
    ),
):
    return admin_service.list_logs(db, limit=limit)


@router.patch("/user/{user_id}/freeze", response_model=schemas.UserRead)
def set_user_freeze(
    user_id: int,
    payload: UserFreezeUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("account.freeze")
    ),
):
    return admin_service.set_user_freeze(
        db,
        user_id,
        is_frozen=payload.is_frozen,
        reason=payload.reason,
        support_case_id=payload.support_case_id,
        admin_user=current_admin,
    )


@router.patch("/user/{user_id}/role", response_model=schemas.UserRead)
def set_admin_role(
    user_id: int,
    payload: AdminRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("admin.roles")
    ),
):
    if user_id == current_admin.id and (
        not payload.enabled or payload.role != "admin"
    ):
        raise HTTPException(
            status_code=400,
            detail="Administrators cannot demote or revoke their own access",
        )
    return admin_service.set_admin_role(
        db,
        user_id,
        role=payload.role,
        enabled=payload.enabled,
        reason=payload.reason,
        support_case_id=payload.support_case_id,
        admin_user=current_admin,
    )


@router.patch("/city/{city_id}/resources", response_model=schemas.CityRead)
def modify_city_resources(
    city_id: int,
    payload: ResourceUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("game.correct")
    ),
):
    updates = payload.model_dump(
        exclude={"reason", "support_case_id"}, exclude_unset=True
    )
    return admin_service.update_city_resources(
        db,
        city_id,
        updates,
        current_admin,
        reason=payload.reason,
        support_case_id=payload.support_case_id,
    )


@router.patch("/city/{city_id}/building/{building_type}", response_model=schemas.BuildingRead)
def set_building_level(
    city_id: int,
    building_type: str,
    payload: BuildingLevelUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("game.correct")
    ),
):
    return admin_service.set_building_level(
        db,
        city_id,
        building_type,
        payload.new_level,
        current_admin,
        reason=payload.reason,
        support_case_id=payload.support_case_id,
    )


@router.patch("/city/{city_id}/troops", response_model=List[schemas.TroopRead])
def set_troop_amounts(
    city_id: int,
    payload: TroopUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("game.correct")
    ),
):
    return admin_service.set_troop_amounts(
        db,
        city_id,
        payload.troops,
        current_admin,
        reason=payload.reason,
        support_case_id=payload.support_case_id,
    )


@router.post("/city/create", response_model=schemas.CityRead)
def create_city(
    payload: AdminCityCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("game.correct")
    ),
):
    return admin_service.create_city(
        db,
        payload.model_dump(exclude={"reason", "support_case_id"}),
        current_admin,
        reason=payload.reason,
        support_case_id=payload.support_case_id,
    )


@router.patch("/city/{city_id}/coordinates", response_model=schemas.CityRead)
def teleport_city(
    city_id: int,
    payload: CoordinatesUpdate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("game.correct")
    ),
):
    return admin_service.teleport_city(
        db,
        city_id,
        payload.x,
        payload.y,
        current_admin,
        reason=payload.reason,
        support_case_id=payload.support_case_id,
    )


@router.post("/logs/{log_id}/revert", response_model=schemas.LogRead)
def revert_admin_action(
    log_id: int,
    payload: RevertRequest,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("audit.read")
    ),
):
    return admin_service.revert_action(
        db,
        log_id,
        admin_user=current_admin,
        reason=payload.reason,
    )

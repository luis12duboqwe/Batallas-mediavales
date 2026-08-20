"""Movement endpoints for creating and inspecting marches."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..routers.responses import error_response
from ..services import movement, protection

router = APIRouter(tags=["movements"])

HOSTILE_PLAYER_MOVEMENT_TYPES = {"attack", "spy"}


@router.post("/", response_model=schemas.MovementRead)
def create_movement(
    payload: schemas.MovementCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a movement; world simulation remains worker-only."""

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
        raise error_response(
            404,
            "origin_not_found",
            "Origin city not found",
            {"city_id": payload.origin_city_id},
        )

    target_city = None
    if payload.target_city_id is not None:
        target_city = (
            db.query(models.City)
            .options(selectinload(models.City.owner), selectinload(models.City.world))
            .filter(
                models.City.id == payload.target_city_id,
                models.City.world_id == payload.world_id,
            )
            .first()
        )
        if not target_city:
            raise error_response(
                404,
                "target_not_found",
                "Target city not found",
                {"city_id": payload.target_city_id},
            )

        is_hostile_pvp = (
            payload.movement_type in HOSTILE_PLAYER_MOVEMENT_TYPES
            and target_city.owner is not None
            and target_city.owner_id != current_user.id
        )
        if is_hostile_pvp:
            if protection.is_user_protected(current_user):
                raise error_response(
                    400,
                    "protection_active",
                    "Protected players cannot launch PvP hostilities",
                )
            if protection.is_user_protected(target_city.owner):
                raise error_response(
                    400,
                    "target_protected",
                    "Target player is under protection",
                )
    elif payload.target_oasis_id is not None:
        target_oasis = (
            db.query(models.Oasis)
            .filter(
                models.Oasis.id == payload.target_oasis_id,
                models.Oasis.world_id == payload.world_id,
            )
            .first()
        )
        if not target_oasis:
            raise error_response(
                404,
                "target_not_found",
                "Target oasis not found",
                {"oasis_id": payload.target_oasis_id},
            )
    else:
        raise error_response(
            400,
            "invalid_target",
            "Must specify target_city_id or target_oasis_id",
        )

    try:
        return movement.send_movement(
            db,
            origin_city,
            payload.target_city_id,
            payload.movement_type,
            troops=payload.troops,
            resources=payload.resources,
            spy_count=payload.spy_count,
            target_city=target_city,
            target_building=payload.target_building,
            target_oasis_id=payload.target_oasis_id,
        )
    except ValueError as exc:
        raise error_response(400, "movement_creation_failed", str(exc)) from exc


@router.get("/", response_model=list[schemas.MovementRead])
def list_movements(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List movements related to the current user's cities without resolving them."""

    user_city_ids = [city.id for city in current_user.cities if city.world_id == world_id]
    if not user_city_ids:
        return []

    return (
        db.query(models.Movement)
        .filter(
            models.Movement.world_id == world_id,
            (
                models.Movement.origin_city_id.in_(user_city_ids)
                | models.Movement.target_city_id.in_(user_city_ids)
            ),
        )
        .order_by(models.Movement.created_at.desc())
        .all()
    )

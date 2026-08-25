from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import adventure as adventure_service
from ..services import hero as hero_service
from .responses import error_response
from .world_access import require_world_access

router = APIRouter(
    prefix="/adventure",
    tags=["adventure"],
    dependencies=[Depends(require_world_access)],
)


def _hero(db: Session, user_id: int, world_id: int) -> models.Hero:
    try:
        return hero_service.get_hero(db, user_id, world_id)
    except ValueError as exc:
        raise error_response(400, "hero_access_failed", str(exc)) from exc
    except RuntimeError as exc:
        raise error_response(409, "hero_rules_mismatch", str(exc)) from exc


@router.get("/", response_model=list[schemas.AdventureRead])
def get_adventures(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = _hero(db, current_user.id, world_id)
    return adventure_service.get_adventures(db, hero)


@router.post("/{adventure_id}/start", response_model=schemas.AdventureRead)
def start_adventure(
    adventure_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = _hero(db, current_user.id, world_id)
    try:
        return adventure_service.start_adventure(db, adventure_id, hero)
    except ValueError as exc:
        raise error_response(400, "adventure_start_failed", str(exc)) from exc


@router.post("/{adventure_id}/claim", response_model=schemas.AdventureClaimResponse)
def claim_adventure(
    adventure_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = _hero(db, current_user.id, world_id)
    try:
        return adventure_service.claim_adventure(db, adventure_id, hero)
    except ValueError as exc:
        raise error_response(400, "adventure_claim_failed", str(exc)) from exc

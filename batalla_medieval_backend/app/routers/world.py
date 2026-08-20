from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import world_gen, world_membership

router = APIRouter(prefix="/worlds", tags=["worlds"])


@router.get("/", response_model=list[schemas.WorldRead])
def list_worlds(db: Session = Depends(get_db)):
    # Return all worlds so users can see history/winners
    return db.query(models.World).order_by(models.World.is_active.desc(), models.World.created_at.desc()).all()


@router.post("/create", response_model=schemas.WorldRead)
def create_world(
    payload: schemas.WorldCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can create worlds")
    world = models.World(
        name=payload.name,
        speed_modifier=payload.speed_modifier,
        resource_modifier=payload.resource_modifier,
        is_active=payload.is_active,
        special_rules=payload.special_rules,
        map_size=payload.map_size,
    )
    db.add(world)
    db.commit()
    db.refresh(world)
    return world


def _join_or_select_world(
    db: Session,
    current_user: models.User,
    world_id: int,
) -> models.PlayerWorld:
    try:
        return world_membership.join_world(db, current_user, world_id)
    except world_membership.WorldNotAvailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except world_membership.SpawnUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except world_membership.StartingCityConsistencyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{world_id}/join", response_model=schemas.PlayerWorldRead)
def join_world(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Join a world and guarantee an idempotent starting city."""

    return _join_or_select_world(db, current_user, world_id)


@router.get("/active", response_model=schemas.ActiveWorldSnapshot)
def get_active_world(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    worlds = db.query(models.World).filter(models.World.is_active.is_(True)).all()
    return {"current_world_id": current_user.world_id, "worlds": worlds}


@router.post("/active", response_model=schemas.PlayerWorldRead)
def set_active_world(
    payload: schemas.WorldSelect,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Select a world; first selection performs the same safe onboarding."""

    return _join_or_select_world(db, current_user, payload.world_id)


@router.get("/{world_id}/tiles", response_model=list[schemas.MapTile])
def get_map_tiles(
    world_id: int,
    min_x: int,
    max_x: int,
    min_y: int,
    max_y: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Validate range to prevent fetching too many tiles
    if (max_x - min_x) * (max_y - min_y) > 2500:
        raise HTTPException(status_code=400, detail="Area too large")

    tiles = []
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            tile_type = world_gen.get_tile_type(x, y)
            tiles.append(schemas.MapTile(x=x, y=y, type=tile_type))

    return tiles

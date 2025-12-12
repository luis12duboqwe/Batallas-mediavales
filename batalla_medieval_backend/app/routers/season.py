from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import season as season_service

router = APIRouter(tags=["season"])


def require_admin(current_user: models.User = Depends(get_current_user)):
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


@router.post("/start", response_model=schemas.SeasonRead)
def start_season(
    payload: schemas.SeasonCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    return season_service.start_new_season(db, payload.world_id, payload.name)


@router.post("/end", response_model=list[schemas.SeasonResultRead])
def end_season(
    world_id: str,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    results = season_service.end_current_season(db, world_id)
    return [
        schemas.SeasonResultRead(
            user_id=result.user_id,
            alliance_id=result.alliance_id,
            rank=result.rank,
            points=result.points,
            rewards=result.get_rewards(),
        )
        for result in results
    ]


@router.get("/info", response_model=schemas.SeasonInfo)
def get_season_info(db: Session = Depends(get_db)):
    info = season_service.get_season_info(db)
    active = info.get("active_season")
    return schemas.SeasonInfo(
        active_season=active,
        latest_results=[
            schemas.SeasonResultRead(
                user_id=result.user_id,
                alliance_id=result.alliance_id,
                rank=result.rank,
                points=result.points,
                rewards=result.get_rewards(),
            )
            for result in info.get("latest_results", [])
        ],
    )

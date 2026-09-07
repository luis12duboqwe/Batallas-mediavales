from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import admin as admin_service
from ..services import admin_permissions
from ..services import season as season_service

router = APIRouter(tags=["season"])


def _season_snapshot(season: models.Season | None) -> dict | None:
    if season is None:
        return None
    return {
        "id": season.id,
        "season_id": season.season_id,
        "world_id": season.world_id,
        "name": season.name,
        "is_active": bool(season.is_active),
        "start_date": season.start_date.isoformat() if season.start_date else None,
        "end_date": season.end_date.isoformat() if season.end_date else None,
    }


@router.post("/start", response_model=schemas.SeasonRead)
def start_season(
    payload: schemas.SeasonCreate,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("admin.manage")
    ),
    reason: str = Depends(admin_permissions.require_reason),
):
    previous = (
        db.query(models.Season)
        .filter(
            models.Season.world_id == str(payload.world_id),
            models.Season.is_active.is_(True),
        )
        .first()
    )
    before = _season_snapshot(previous)
    season = season_service.start_new_season(db, payload.world_id, payload.name)
    admin_service.log_action(
        db,
        current_admin.id,
        "start_season",
        {"world_id": str(payload.world_id)},
        target_type="season",
        target_id=season.id,
        reason=reason,
        before_state=before,
        after_state=_season_snapshot(season),
        reversible=False,
    )
    db.commit()
    return season


@router.post("/end", response_model=list[schemas.SeasonResultRead])
def end_season(
    world_id: str,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(
        admin_permissions.require_capability("admin.manage")
    ),
    reason: str = Depends(admin_permissions.require_reason),
):
    active = (
        db.query(models.Season)
        .filter(
            models.Season.world_id == str(world_id),
            models.Season.is_active.is_(True),
        )
        .first()
    )
    before = _season_snapshot(active)
    results = season_service.end_current_season(db, world_id)
    ended = db.query(models.Season).filter(models.Season.id == active.id).one() if active else None
    admin_service.log_action(
        db,
        current_admin.id,
        "end_season",
        {"world_id": str(world_id), "result_count": len(results)},
        target_type="season",
        target_id=ended.id if ended else None,
        reason=reason,
        before_state=before,
        after_state=_season_snapshot(ended),
        reversible=False,
    )
    db.commit()
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

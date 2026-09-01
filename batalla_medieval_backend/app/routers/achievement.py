from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import achievement as achievement_service
from .world_access import require_open_world_access, require_world_access

router = APIRouter(prefix="/achievement", tags=["achievement"])


@router.get("/list", response_model=list[schemas.AchievementWithProgress])
def list_achievements(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    _: models.PlayerWorld = Depends(require_world_access),
):
    entries = achievement_service.get_user_achievements(db, current_user, world_id)
    return [
        schemas.AchievementWithProgress(
            achievement=schemas.AchievementRead.model_validate(achievement),
            progress=schemas.AchievementProgressRead.model_validate(progress),
        )
        for achievement, progress in entries
    ]


@router.post("/claim/{achievement_id}", response_model=schemas.AchievementProgressRead)
def claim_achievement(
    achievement_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    _: models.PlayerWorld = Depends(require_world_access),
    _open: models.PlayerWorld = Depends(require_open_world_access),
):
    progress = achievement_service.claim_achievement(
        db,
        current_user,
        world_id,
        achievement_id,
    )
    return schemas.AchievementProgressRead.model_validate(progress)

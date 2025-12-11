from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import achievement as achievement_service

router = APIRouter(prefix="/achievement", tags=["achievement"])


@router.get("/list", response_model=list[schemas.AchievementWithProgress])
def list_achievements(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    entries = achievement_service.get_user_achievements(db, current_user)
    return [
        schemas.AchievementWithProgress(
            achievement=schemas.AchievementRead.from_orm(achievement),
            progress=schemas.AchievementProgressRead.from_orm(progress),
        )
        for achievement, progress in entries
    ]


@router.post("/claim/{achievement_id}", response_model=schemas.AchievementProgressRead)
def claim_achievement(
    achievement_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    progress = achievement_service.claim_achievement(db, current_user, achievement_id)
    return schemas.AchievementProgressRead.from_orm(progress)

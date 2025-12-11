from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import quest as quest_service

router = APIRouter(prefix="/quest", tags=["quest"])


@router.get("/list", response_model=schemas.QuestListResponse)
def list_quests(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    progresses = quest_service.list_quests_for_user(db, current_user)
    serialized = [quest_service.serialize_progress(p) for p in progresses]
    return schemas.QuestListResponse(
        quests=serialized, tutorial_completed=quest_service.tutorial_completed(progresses)
    )


@router.post("/claim/{quest_id}", response_model=schemas.QuestClaimResponse)
def claim_quest(
    quest_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    try:
        progress, reward = quest_service.claim_reward(db, current_user, quest_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    quest_data = quest_service.serialize_progress(progress)
    return schemas.QuestClaimResponse(quest=quest_data, granted_reward=reward)

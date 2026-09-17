from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import quest as quest_service
from ..services import tutorial as tutorial_service

router = APIRouter(tags=["quest"])


@router.get("/list", response_model=schemas.QuestListResponse)
def list_quests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Compatibility endpoint backed by the canonical tutorial state.

    The retired quest catalogue is intentionally not exposed. Existing clients
    still receive a valid response while the completion bit comes from the same
    server-authoritative tutorial used by the current UI.
    """

    progress = tutorial_service.get_progress(db, current_user)
    return schemas.QuestListResponse(
        quests=[],
        tutorial_completed=bool(progress["completed"]),
    )


@router.post("/claim/{quest_id}", response_model=schemas.QuestClaimResponse)
def claim_quest(
    quest_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ = (quest_id, db, current_user)
    raise HTTPException(
        status_code=410,
        detail=quest_service.LEGACY_QUEST_RETIREMENT_MESSAGE,
    )

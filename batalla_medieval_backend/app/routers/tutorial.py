from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import tutorial as tutorial_service

router = APIRouter(tags=["tutorial"])


class TutorialUpdate(BaseModel):
    step: int | None = None


@router.post("/advance")
def advance_tutorial(
    update: TutorialUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Refresh tutorial progress without trusting a client-supplied step."""

    _ = update.step  # Backwards-compatible request body; intentionally ignored.
    return tutorial_service.sync_progress(db, current_user)


@router.get("/status")
def get_tutorial_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return tutorial_service.sync_progress(db, current_user)

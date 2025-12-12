from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .. import models
from ..database import get_db
from ..routers.auth import get_current_user

router = APIRouter(tags=["tutorial"])

class TutorialUpdate(BaseModel):
    step: int

@router.post("/advance")
def advance_tutorial(
    update: TutorialUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if update.step <= current_user.tutorial_step:
        return {"message": "Already at this step or higher", "step": current_user.tutorial_step}
    
    current_user.tutorial_step = update.step
    db.commit()
    return {"message": "Tutorial advanced", "step": current_user.tutorial_step}

@router.get("/status")
def get_tutorial_status(
    current_user: models.User = Depends(get_current_user)
):
    return {"step": current_user.tutorial_step}

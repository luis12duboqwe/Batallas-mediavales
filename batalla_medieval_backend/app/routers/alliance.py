from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import admin

router = APIRouter(prefix="/alliances", tags=["alliances"])


@router.post("/", response_model=schemas.AllianceRead)
def create_alliance(
    payload: schemas.AllianceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if db.query(models.Alliance).filter(models.Alliance.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Alliance name already used")
    alliance = admin.create_alliance(db, payload, current_user)
    return alliance


@router.get("/", response_model=list[schemas.AllianceRead])
def list_alliances(db: Session = Depends(get_db)):
    return db.query(models.Alliance).all()

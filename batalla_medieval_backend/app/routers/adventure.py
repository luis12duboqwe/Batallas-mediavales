from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import adventure as adventure_service
from ..services import hero as hero_service

router = APIRouter(
    prefix="/adventure",
    tags=["adventure"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=list[schemas.AdventureRead])
def get_adventures(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    hero = hero_service.get_hero(db, current_user.id)
    return adventure_service.get_adventures(db, hero.id)

@router.post("/{adventure_id}/start", response_model=schemas.AdventureRead)
def start_adventure(
    adventure_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    hero = hero_service.get_hero(db, current_user.id)
    try:
        return adventure_service.start_adventure(db, adventure_id, hero)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{adventure_id}/claim", response_model=schemas.AdventureClaimResponse)
def claim_adventure(
    adventure_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    hero = hero_service.get_hero(db, current_user.id)
    try:
        return adventure_service.claim_adventure(db, adventure_id, hero)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

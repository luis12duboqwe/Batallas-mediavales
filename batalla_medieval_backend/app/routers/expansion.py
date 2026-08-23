from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import expansion

router = APIRouter(prefix="/expansion", tags=["expansion"])


@router.get("/status", response_model=schemas.ExpansionStatus)
def expansion_status(
    world_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        return expansion.get_expansion_status(
            db,
            user_id=current_user.id,
            world_id=world_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/found", response_model=schemas.CityRead)
def found_settlement(
    payload: schemas.FoundSettlementRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    origin = (
        db.query(models.City)
        .filter(
            models.City.id == payload.origin_city_id,
            models.City.owner_id == current_user.id,
        )
        .one_or_none()
    )
    if origin is None:
        raise HTTPException(status_code=404, detail="Origin settlement not found")

    try:
        return expansion.found_settlement(
            db,
            current_user,
            origin,
            payload.name,
            payload.x,
            payload.y,
            payload.settlement_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/camps/{camp_id}/promote", response_model=schemas.CityRead)
def promote_camp(
    camp_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    camp = (
        db.query(models.City)
        .filter(
            models.City.id == camp_id,
            models.City.owner_id == current_user.id,
        )
        .one_or_none()
    )
    if camp is None:
        raise HTTPException(status_code=404, detail="Camp not found")

    try:
        return expansion.promote_camp(db, current_user, camp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

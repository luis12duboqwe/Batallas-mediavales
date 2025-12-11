from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import conquest

router = APIRouter(prefix="/conquest", tags=["conquest"])


@router.post("/attack", response_model=schemas.ConquestResult)
def attack_city(
    payload: schemas.ConquestRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    attacker_city = (
        db.query(models.City)
        .filter(models.City.id == payload.origin_city_id, models.City.owner_id == current_user.id)
        .first()
    )
    if not attacker_city:
        raise HTTPException(status_code=404, detail="Origin city not found")

    target_city = db.query(models.City).filter(models.City.id == payload.target_city_id).first()
    if not target_city:
        raise HTTPException(status_code=404, detail="Target city not found")

    try:
        victory, conquered = conquest.resolve_conquest(db, attacker_city, target_city, payload.troops)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return schemas.ConquestResult(
        victory=victory,
        conquered=conquered,
        loyalty=target_city.loyalty,
    )


@router.post("/found", response_model=schemas.CityRead)
def found_new_city(
    payload: schemas.FoundCityRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    origin_city = (
        db.query(models.City)
        .filter(models.City.id == payload.origin_city_id, models.City.owner_id == current_user.id)
        .first()
    )
    if not origin_city:
        raise HTTPException(status_code=404, detail="Origin city not found")

    try:
        new_city = conquest.found_city(db, current_user, origin_city, payload.name, payload.x, payload.y)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return new_city

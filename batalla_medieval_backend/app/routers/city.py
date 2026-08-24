from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import production, protection, quest as quest_service

router = APIRouter(tags=["cities"])


@router.post("/", response_model=schemas.CityRead)
def create_city(
    city: schemas.CityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    del city, db, current_user
    raise HTTPException(
        status_code=409,
        detail=(
            "Direct city creation is disabled. Join a world for the initial capital "
            "or use /expansion/found for additional settlements."
        ),
    )


@router.get("/", response_model=list[schemas.CityRead])
def list_cities(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cities = (
        db.query(models.City)
        .filter(models.City.owner_id == current_user.id, models.City.world_id == world_id)
        .all()
    )
    for city in cities:
        city, gains = production.recalculate_resources(db, city, return_gains=True)
        quest_service.handle_event(db, current_user, "resources_collected", gains)
        city.is_protected = protection.is_user_protected(city.owner)
    return cities


@router.get("/{city_id}", response_model=schemas.CityRead)
def get_city(
    city_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = (
        db.query(models.City)
        .filter(
            models.City.id == city_id,
            models.City.owner_id == current_user.id,
            models.City.world_id == world_id,
        )
        .first()
    )
    if not city:
        raise HTTPException(status_code=404, detail="City not found")
    city, gains = production.recalculate_resources(db, city, return_gains=True)
    quest_service.handle_event(db, current_user, "resources_collected", gains)
    city.is_protected = protection.is_user_protected(city.owner)
    return city


@router.get("/{city_id}/status", response_model=schemas.CityResourceStatus)
def city_status(
    city_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = (
        db.query(models.City)
        .filter(
            models.City.id == city_id,
            models.City.owner_id == current_user.id,
            models.City.world_id == world_id,
        )
        .first()
    )
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    city, _ = production.recalculate_resources(db, city, return_gains=True)
    storage_limit = production.get_storage_limit(city)
    production_per_hour = production.get_production_per_hour(db, city)
    building_queue = (
        db.query(models.BuildingQueue)
        .filter(models.BuildingQueue.city_id == city.id)
        .all()
    )
    troop_queue = (
        db.query(models.TroopQueue)
        .filter(models.TroopQueue.city_id == city.id)
        .all()
    )
    return schemas.CityResourceStatus(
        city_id=city.id,
        settlement_type=city.settlement_type,
        wood=city.wood,
        stone=city.stone,
        iron=city.iron,
        gold=city.gold,
        loyalty=city.loyalty,
        storage_limit=storage_limit,
        production_per_hour=production_per_hour,
        last_production=city.last_production,
        is_protected=protection.is_user_protected(city.owner),
        building_queue=building_queue,
        troop_queue=troop_queue,
    )

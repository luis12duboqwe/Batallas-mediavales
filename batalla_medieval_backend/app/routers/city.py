from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import (
    production,
    protection,
    quest as quest_service,
    unit_catalog,
    upkeep as upkeep_service,
)

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


def _decorate_population_capacity(city: models.City) -> None:
    """Expose effective capacity without mutating the persisted base column."""

    city.population_capacity = unit_catalog.get_population_capacity(city)


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
        if getattr(city.world, "lifecycle_status", "open") == "open" and any(float(value) > 0 for value in gains.values()):
            quest_service.handle_event(db, current_user, "resources_collected", gains)
        _decorate_population_capacity(city)
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
    if getattr(city.world, "lifecycle_status", "open") == "open" and any(float(value) > 0 for value in gains.values()):
        quest_service.handle_event(db, current_user, "resources_collected", gains)
    _decorate_population_capacity(city)
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
    gross_production_per_hour = production.get_gross_production_per_hour(db, city)
    production_per_hour = production.get_production_per_hour(db, city)
    upkeep_status = upkeep_service.get_upkeep_status(db, city)
    population_used = unit_catalog.get_population_used(db, city)
    population_capacity = unit_catalog.get_population_capacity(city)
    population_available = max(
        population_capacity
        - population_used
        - unit_catalog.get_population_reserved_for_training(db, city.id),
        0,
    )
    building_queue = (
        db.query(models.BuildingQueue)
        .filter(models.BuildingQueue.city_id == city.id)
        .all()
    )
    research_queue = (
        db.query(models.ResearchQueue)
        .filter(models.ResearchQueue.city_id == city.id)
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
        population=population_used,
        population_max=population_capacity,
        population_used=population_used,
        population_capacity=population_capacity,
        population_available=population_available,
        loyalty=city.loyalty,
        storage_limit=storage_limit,
        production_per_hour=production_per_hour,
        gross_production_per_hour=gross_production_per_hour,
        net_gold_per_hour=float(production_per_hour[upkeep_service.UPKEEP_RESOURCE]),
        upkeep_used_per_hour=float(upkeep_status["used_per_hour"]),
        upkeep_reserved_per_hour=float(upkeep_status["reserved_per_hour"]),
        upkeep_capacity_per_hour=float(upkeep_status["capacity_per_hour"]),
        upkeep_available_per_hour=float(upkeep_status["available_per_hour"]),
        upkeep_sustainable=bool(upkeep_status["sustainable"]),
        last_production=city.last_production,
        is_protected=protection.is_user_protected(city.owner),
        building_queue=building_queue,
        research_queue=research_queue,
        troop_queue=troop_queue,
    )
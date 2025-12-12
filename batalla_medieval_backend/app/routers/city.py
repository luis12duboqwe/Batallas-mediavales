from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import production, protection, quest as quest_service, world_gen

router = APIRouter(tags=["cities"])


@router.post("/", response_model=schemas.CityRead)
def create_city(
    city: schemas.CityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    world = db.query(models.World).filter(models.World.id == city.world_id, models.World.is_active.is_(True)).first()
    if not world:
        raise HTTPException(status_code=404, detail="World not found or inactive")

    # Automatic spawning if coordinates are not provided
    if city.x is None or city.y is None:
        try:
            city.x, city.y = world_gen.find_spawn_location(db, city.world_id, world.map_size)
        except ValueError:
            raise HTTPException(status_code=500, detail="No valid spawn location found")
    
    if city.x < 0 or city.y < 0 or city.x >= world.map_size or city.y >= world.map_size:
        raise HTTPException(status_code=400, detail="Invalid coordinates for this world")
    occupied = (
        db.query(models.City)
        .filter(models.City.world_id == city.world_id, models.City.x == city.x, models.City.y == city.y)
        .first()
    )
    if occupied:
        raise HTTPException(status_code=409, detail="Coordinates already occupied")
    membership = (
        db.query(models.PlayerWorld)
        .filter(models.PlayerWorld.user_id == current_user.id, models.PlayerWorld.world_id == city.world_id)
        .first()
    )
    if not membership:
        membership = models.PlayerWorld(user_id=current_user.id, world_id=city.world_id)
        db.add(membership)
        db.commit()
        db.refresh(membership)
    current_user.world_id = city.world_id
    db.add(current_user)
    
    # Determine tile type
    tile_type = world_gen.get_tile_type(city.x, city.y)
    
    db_city = models.City(
        name=city.name,
        x=city.x,
        y=city.y,
        owner_id=current_user.id,
        world_id=city.world_id,
        tile_type=tile_type
    )
    db.add(db_city)
    db.commit()
    db.refresh(db_city)
    production.recalculate_resources(db, db_city)
    return db_city


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
        wood=city.wood,
        clay=city.clay,
        iron=city.iron,
        loyalty=city.loyalty,
        storage_limit=storage_limit,
        production_per_hour=production_per_hour,
        last_production=city.last_production,
        is_protected=protection.is_user_protected(city.owner),
        building_queue=building_queue,
        troop_queue=troop_queue,
    )

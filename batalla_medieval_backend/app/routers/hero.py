from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import hero as hero_service

router = APIRouter(
    prefix="/hero",
    tags=["hero"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_model=schemas.HeroRead)
def get_my_hero(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = hero_service.get_hero(db, current_user.id)
    
    # Calculate next level xp (simple lookup or calc)
    # We need to expose the XP table or calc it here
    # For simplicity, let's just use the service logic or duplicate it slightly for display
    # Ideally service should return a rich object or schema should have a computed field
    
    # Let's add available_points and next_level_xp to the response manually if not in model
    available = hero_service.get_available_points(hero)
    next_xp = hero_service.XP_TABLE[hero.level] if hero.level < 100 else 0
    
    return schemas.HeroRead(
        id=hero.id,
        user_id=hero.user_id,
        city_id=hero.city_id,
        name=hero.name,
        level=hero.level,
        xp=hero.xp,
        next_level_xp=next_xp,
        health=hero.health,
        status=hero.status,
        attack_points=hero.attack_points,
        defense_points=hero.defense_points,
        production_points=hero.production_points,
        available_points=available
    )

@router.post("/distribute", response_model=schemas.HeroRead)
def distribute_points(
    points: schemas.HeroDistributePoints,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = hero_service.get_hero(db, current_user.id)
    try:
        hero_service.distribute_points(db, hero, points.attack, points.defense, points.production)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # Return updated hero
    available = hero_service.get_available_points(hero)
    next_xp = hero_service.XP_TABLE[hero.level] if hero.level < 100 else 0
    
    return schemas.HeroRead(
        id=hero.id,
        user_id=hero.user_id,
        city_id=hero.city_id,
        name=hero.name,
        level=hero.level,
        xp=hero.xp,
        next_level_xp=next_xp,
        health=hero.health,
        status=hero.status,
        attack_points=hero.attack_points,
        defense_points=hero.defense_points,
        production_points=hero.production_points,
        available_points=available
    )

@router.post("/revive", response_model=schemas.HeroRead)
def revive_hero(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = hero_service.get_hero(db, current_user.id)
    try:
        hero_service.revive_hero(db, hero)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    available = hero_service.get_available_points(hero)
    next_xp = hero_service.XP_TABLE[hero.level] if hero.level < 100 else 0
    
    return schemas.HeroRead(
        id=hero.id,
        user_id=hero.user_id,
        city_id=hero.city_id,
        name=hero.name,
        level=hero.level,
        xp=hero.xp,
        next_level_xp=next_xp,
        health=hero.health,
        status=hero.status,
        attack_points=hero.attack_points,
        defense_points=hero.defense_points,
        production_points=hero.production_points,
        available_points=available
    )

@router.get("/items", response_model=list[schemas.HeroItemRead])
def get_inventory(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = hero_service.get_hero(db, current_user.id)
    return hero.items

@router.post("/items/{item_id}/equip", response_model=list[schemas.HeroItemRead])
def equip_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = hero_service.get_hero(db, current_user.id)
    try:
        hero_service.equip_item(db, hero, item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return hero.items

@router.post("/items/{item_id}/unequip", response_model=list[schemas.HeroItemRead])
def unequip_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = hero_service.get_hero(db, current_user.id)
    try:
        hero_service.unequip_item(db, hero, item_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return hero.items

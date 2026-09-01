from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import hero as hero_service
from ..services import hero_rules
from .world_access import require_open_world_access, require_world_access

router = APIRouter(
    prefix="/hero",
    tags=["hero"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(require_world_access)],
)


def _read(hero: models.Hero) -> schemas.HeroRead:
    next_xp = hero_service.XP_TABLE[hero.level] if hero.level < hero_rules.HERO_MAX_LEVEL else 0
    return schemas.HeroRead(
        id=hero.id,
        user_id=hero.user_id,
        world_id=hero.world_id,
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
        available_points=hero_service.get_available_points(hero),
        rules_version=hero_rules.HERO_RULES_VERSION,
    )


@router.get("/", response_model=schemas.HeroRead)
def get_my_hero(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        return _read(hero_service.get_hero(db, current_user.id, world_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/distribute", response_model=schemas.HeroRead)
def distribute_points(
    points: schemas.HeroDistributePoints,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    _: models.PlayerWorld = Depends(require_open_world_access),
):
    try:
        hero = hero_service.get_hero(db, current_user.id, world_id)
        updated = hero_service.distribute_points(
            db,
            hero,
            points.attack,
            points.defense,
            points.production,
        )
        return _read(updated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/revive", response_model=schemas.HeroRead)
def revive_hero(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    _: models.PlayerWorld = Depends(require_open_world_access),
):
    try:
        hero = hero_service.get_hero(db, current_user.id, world_id)
        return _read(hero_service.revive_hero(db, hero))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/items", response_model=list[schemas.HeroItemRead])
def get_inventory(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        hero = hero_service.get_hero(db, current_user.id, world_id)
        return hero.items
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/items/{item_id}/equip", response_model=list[schemas.HeroItemRead])
def equip_item(
    item_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    _: models.PlayerWorld = Depends(require_open_world_access),
):
    try:
        hero = hero_service.get_hero(db, current_user.id, world_id)
        return hero_service.equip_item(db, hero, item_id).items
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/items/{item_id}/unequip", response_model=list[schemas.HeroItemRead])
def unequip_item(
    item_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    _: models.PlayerWorld = Depends(require_open_world_access),
):
    try:
        hero = hero_service.get_hero(db, current_user.id, world_id)
        return hero_service.unequip_item(db, hero, item_id).items
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

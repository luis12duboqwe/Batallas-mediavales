from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..services import hero as hero_service, hero_rules
from .responses import error_response
from .world_access import require_world_access

router = APIRouter(
    prefix="/hero",
    tags=["hero"],
    dependencies=[Depends(require_world_access)],
)


def _hero_payload(hero: models.Hero) -> schemas.HeroRead:
    next_xp = (
        hero_service.XP_TABLE[hero.level]
        if hero.level < hero_rules.HERO_LEVEL_CAP
        else 0
    )
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
        bonuses=hero_service.calculate_total_bonuses(hero),
        revive_cost=hero_service.revive_cost(hero),
    )


def _get_hero(db: Session, current_user: models.User, world_id: int) -> models.Hero:
    try:
        return hero_service.get_hero(db, current_user.id, world_id)
    except ValueError as exc:
        raise error_response(400, "hero_access_failed", str(exc)) from exc
    except RuntimeError as exc:
        raise error_response(409, "hero_rules_mismatch", str(exc)) from exc


@router.get("/", response_model=schemas.HeroRead)
def get_my_hero(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _hero_payload(_get_hero(db, current_user, world_id))


@router.post("/distribute", response_model=schemas.HeroRead)
def distribute_points(
    points: schemas.HeroDistributePoints,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = _get_hero(db, current_user, world_id)
    try:
        updated = hero_service.distribute_points(
            db,
            hero,
            points.attack,
            points.defense,
            points.production,
        )
    except ValueError as exc:
        raise error_response(400, "hero_points_invalid", str(exc)) from exc
    return _hero_payload(updated)


@router.post("/revive", response_model=schemas.HeroRead)
def revive_hero(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = _get_hero(db, current_user, world_id)
    try:
        updated = hero_service.revive_hero(db, hero)
    except ValueError as exc:
        raise error_response(400, "hero_revive_failed", str(exc)) from exc
    return _hero_payload(updated)


@router.get("/items", response_model=list[schemas.HeroItemRead])
def get_inventory(
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = _get_hero(db, current_user, world_id)
    return [hero_service.item_payload(item) for item in hero.items]


@router.post("/items/{item_id}/equip", response_model=list[schemas.HeroItemRead])
def equip_item(
    item_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = _get_hero(db, current_user, world_id)
    try:
        updated = hero_service.equip_item(db, hero, item_id)
    except ValueError as exc:
        raise error_response(400, "hero_item_invalid", str(exc)) from exc
    return [hero_service.item_payload(item) for item in updated.items]


@router.post("/items/{item_id}/unequip", response_model=list[schemas.HeroItemRead])
def unequip_item(
    item_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hero = _get_hero(db, current_user, world_id)
    try:
        updated = hero_service.unequip_item(db, hero, item_id)
    except ValueError as exc:
        raise error_response(400, "hero_item_invalid", str(exc)) from exc
    return [hero_service.item_payload(item) for item in updated.items]

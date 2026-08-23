import json
from typing import Dict, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from . import balance, production, ranking


def log_action(db: Session, user_id: int, action: str, details: Dict) -> models.Log:
    log_entry = models.Log(user_id=user_id, action=action, details=json.dumps(details))
    db.add(log_entry)
    return log_entry


def list_logs(db: Session, limit: int = 100) -> list[models.Log]:
    """Return recent audit/anti-abuse logs for authenticated administrators."""

    return (
        db.query(models.Log)
        .order_by(models.Log.timestamp.desc(), models.Log.id.desc())
        .limit(limit)
        .all()
    )


def set_user_freeze(
    db: Session,
    user_id: int,
    *,
    is_frozen: bool,
    reason: str | None,
    admin_user: models.User,
) -> models.User:
    """Freeze/unfreeze an account and revoke existing sessions when state changes."""

    user = db.query(models.User).filter(models.User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin_user.id and is_frozen:
        raise HTTPException(status_code=400, detail="Administrators cannot freeze themselves")

    normalized_reason = (reason or "").strip() or None
    if is_frozen and normalized_reason is None:
        raise HTTPException(status_code=400, detail="Freeze reason is required")

    changed = user.is_frozen != is_frozen
    user.is_frozen = is_frozen
    user.freeze_reason = normalized_reason if is_frozen else None
    if changed:
        user.auth_version += 1

    log_action(
        db,
        admin_user.id,
        "set_user_freeze",
        {
            "target_user_id": user.id,
            "is_frozen": is_frozen,
            "reason": user.freeze_reason,
            "session_revoked": changed,
        },
    )
    db.commit()
    db.refresh(user)
    return user


def create_alliance(db: Session, payload: schemas.AllianceCreate, leader: models.User) -> models.Alliance:
    alliance = models.Alliance(
        name=payload.name,
        description=payload.description,
        diplomacy="neutral",
        leader_id=leader.id,
        world_id=payload.world_id,
    )
    db.add(alliance)
    db.commit()
    db.refresh(alliance)
    member = models.AllianceMember(alliance_id=alliance.id, user_id=leader.id, rank=schemas.RANK_LEADER)
    db.add(member)
    db.commit()
    ranking.recalculate_player_and_alliance_scores(db, leader.id, payload.world_id)
    return alliance


def update_city_resources(
    db: Session,
    city_id: int,
    resource_updates: Dict[str, Optional[float]],
    admin_user: models.User,
) -> models.City:
    city = db.query(models.City).filter(models.City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    applied_updates: Dict[str, float] = {}
    for field, value in resource_updates.items():
        if value is not None and hasattr(city, field):
            setattr(city, field, value)
            applied_updates[field] = value

    log_action(db, admin_user.id, "update_city_resources", {"city_id": city_id, "updates": applied_updates})
    db.commit()
    db.refresh(city)
    return city


def set_building_level(
    db: Session, city_id: int, building_type: str, new_level: int, admin_user: models.User
) -> models.Building:
    city = db.query(models.City).filter(models.City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    building = (
        db.query(models.Building)
        .filter(models.Building.city_id == city.id, models.Building.name == building_type)
        .first()
    )
    if not building:
        building = models.Building(city_id=city.id, name=building_type, level=new_level)
        db.add(building)
    else:
        building.level = new_level

    log_action(
        db,
        admin_user.id,
        "set_building_level",
        {"city_id": city_id, "building_type": building_type, "new_level": new_level},
    )
    db.commit()
    db.refresh(building)
    return building


def set_troop_amounts(
    db: Session, city_id: int, troop_amounts: Dict[str, int], admin_user: models.User
) -> list[models.Troop]:
    city = db.query(models.City).filter(models.City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    updated_troops: list[models.Troop] = []
    for unit_type, quantity in troop_amounts.items():
        troop = (
            db.query(models.Troop)
            .filter(models.Troop.city_id == city.id, models.Troop.unit_type == unit_type)
            .first()
        )
        if not troop:
            troop = models.Troop(city_id=city.id, unit_type=unit_type, quantity=quantity)
            db.add(troop)
        else:
            troop.quantity = quantity
        updated_troops.append(troop)

    log_action(db, admin_user.id, "set_troop_amounts", {"city_id": city_id, "troops": troop_amounts})
    db.commit()
    for troop in updated_troops:
        db.refresh(troop)
    return updated_troops


def create_city(
    db: Session,
    payload: Dict,
    admin_user: models.User,
) -> models.City:
    owner = db.query(models.User).filter(models.User.id == payload["owner_id"]).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")

    world = (
        db.query(models.World)
        .filter(
            models.World.id == payload["world_id"],
            models.World.is_active.is_(True),
        )
        .first()
    )
    if not world:
        raise HTTPException(status_code=404, detail="World not available")

    membership = (
        db.query(models.PlayerWorld)
        .filter(
            models.PlayerWorld.user_id == owner.id,
            models.PlayerWorld.world_id == world.id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=400, detail="Owner has not joined this world")

    occupied = (
        db.query(models.City)
        .filter(
            models.City.world_id == world.id,
            models.City.x == payload.get("x", 0),
            models.City.y == payload.get("y", 0),
        )
        .first()
    )
    if occupied:
        raise HTTPException(status_code=409, detail="Coordinates already occupied in this world")

    defaults = balance.CITY_STARTING_RESOURCES
    city = models.City(
        name=payload["name"],
        x=payload.get("x", 0),
        y=payload.get("y", 0),
        owner_id=owner.id,
        world_id=world.id,
        wood=payload.get("wood", defaults["wood"]),
        stone=payload.get("stone", defaults["stone"]),
        iron=payload.get("iron", defaults["iron"]),
        gold=payload.get("gold", defaults["gold"]),
        population_max=payload.get("population_max", 100),
    )
    db.add(city)
    db.commit()
    db.refresh(city)
    production.recalculate_resources(db, city)
    log_action(
        db,
        admin_user.id,
        "create_city",
        {"city_id": city.id, "owner_id": owner.id, "world_id": world.id},
    )
    db.commit()
    db.refresh(city)
    return city


def teleport_city(db: Session, city_id: int, x: int, y: int, admin_user: models.User) -> models.City:
    city = db.query(models.City).filter(models.City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    occupied = (
        db.query(models.City)
        .filter(
            models.City.world_id == city.world_id,
            models.City.x == x,
            models.City.y == y,
            models.City.id != city.id,
        )
        .first()
    )
    if occupied:
        raise HTTPException(status_code=409, detail="Coordinates already occupied in this world")

    city.x = x
    city.y = y
    log_action(db, admin_user.id, "teleport_city", {"city_id": city_id, "x": x, "y": y})
    db.commit()
    db.refresh(city)
    return city


def delete_user(db: Session, user_id: int, admin_user: models.User) -> None:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    log_action(db, admin_user.id, "delete_user", {"deleted_user_id": user_id})
    db.delete(user)
    db.commit()


def delete_city(db: Session, city_id: int, admin_user: models.User) -> None:
    city = db.query(models.City).filter(models.City.id == city_id).first()
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    log_action(db, admin_user.id, "delete_city", {"deleted_city_id": city_id})
    db.delete(city)
    db.commit()

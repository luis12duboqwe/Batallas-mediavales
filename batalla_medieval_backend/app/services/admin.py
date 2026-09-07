import json
from typing import Dict, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from . import admin_permissions, balance, production, ranking


def _require_reason(reason: str | None) -> str:
    normalized = (reason or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Administrative reason is required")
    return normalized


def _validate_support_case(db: Session, support_case_id: int | None) -> None:
    if support_case_id is None:
        return
    exists = db.query(models.SupportCase.id).filter(models.SupportCase.id == support_case_id).first()
    if exists is None:
        raise HTTPException(status_code=400, detail="Support case not found")


def log_action(
    db: Session,
    user_id: int,
    action: str,
    details: Dict,
    *,
    target_type: str | None = None,
    target_id: int | None = None,
    reason: str | None = None,
    before_state: Dict | None = None,
    after_state: Dict | None = None,
    reversible: bool = False,
    support_case_id: int | None = None,
) -> models.Log:
    log_entry = models.Log(
        user_id=user_id,
        action=action,
        details=json.dumps(details, sort_keys=True),
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        before_state=json.dumps(before_state, sort_keys=True) if before_state is not None else None,
        after_state=json.dumps(after_state, sort_keys=True) if after_state is not None else None,
        reversible=bool(reversible),
        support_case_id=support_case_id,
    )
    db.add(log_entry)
    return log_entry


def list_logs(db: Session, limit: int = 100) -> list[models.Log]:
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
    support_case_id: int | None = None,
) -> models.User:
    normalized_reason = _require_reason(reason)
    _validate_support_case(db, support_case_id)
    user = db.query(models.User).filter(models.User.id == user_id).with_for_update().one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin_user.id and is_frozen:
        raise HTTPException(status_code=400, detail="Administrators cannot freeze themselves")

    before = {"is_frozen": bool(user.is_frozen), "freeze_reason": user.freeze_reason}
    changed = bool(user.is_frozen) != bool(is_frozen)
    user.is_frozen = bool(is_frozen)
    user.freeze_reason = normalized_reason if is_frozen else None
    if changed:
        user.auth_version += 1
    after = {"is_frozen": bool(user.is_frozen), "freeze_reason": user.freeze_reason}

    log_action(
        db,
        admin_user.id,
        "set_user_freeze",
        {"target_user_id": user.id, "session_revoked": changed},
        target_type="user_freeze",
        target_id=user.id,
        reason=normalized_reason,
        before_state=before,
        after_state=after,
        reversible=changed,
        support_case_id=support_case_id,
    )
    db.commit()
    db.refresh(user)
    return user


def set_admin_role(
    db: Session,
    user_id: int,
    *,
    role: str | None,
    enabled: bool,
    reason: str | None,
    admin_user: models.User,
    support_case_id: int | None = None,
) -> models.User:
    normalized_reason = _require_reason(reason)
    _validate_support_case(db, support_case_id)
    user = db.query(models.User).filter(models.User.id == user_id).with_for_update().one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin_user.id and (not enabled or role != "admin"):
        raise HTTPException(
            status_code=400,
            detail="Administrators cannot demote or revoke their own access",
        )
    if enabled and role not in admin_permissions.ADMIN_ROLES:
        raise HTTPException(status_code=400, detail="Invalid administrative role")

    before = {"is_admin": bool(user.is_admin), "admin_role": user.admin_role}
    user.is_admin = bool(enabled)
    user.admin_role = role if enabled else None
    user.auth_version += 1
    after = {"is_admin": bool(user.is_admin), "admin_role": user.admin_role}
    log_action(
        db,
        admin_user.id,
        "set_admin_role",
        {"target_user_id": user.id},
        target_type="user_admin_role",
        target_id=user.id,
        reason=normalized_reason,
        before_state=before,
        after_state=after,
        reversible=False,
        support_case_id=support_case_id,
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
    *,
    reason: str | None,
    support_case_id: int | None = None,
) -> models.City:
    normalized_reason = _require_reason(reason)
    _validate_support_case(db, support_case_id)
    city = db.query(models.City).filter(models.City.id == city_id).with_for_update().one_or_none()
    if city is None:
        raise HTTPException(status_code=404, detail="City not found")

    allowed = {"wood", "stone", "iron", "gold", "population_max"}
    applied = {key: value for key, value in resource_updates.items() if key in allowed and value is not None}
    if not applied:
        raise HTTPException(status_code=400, detail="At least one resource update is required")
    before = {key: getattr(city, key) for key in applied}
    for key, value in applied.items():
        setattr(city, key, value)
    after = {key: getattr(city, key) for key in applied}
    log_action(
        db,
        admin_user.id,
        "update_city_resources",
        {"city_id": city.id, "fields": sorted(applied)},
        target_type="city_resources",
        target_id=city.id,
        reason=normalized_reason,
        before_state=before,
        after_state=after,
        reversible=before != after,
        support_case_id=support_case_id,
    )
    db.commit()
    db.refresh(city)
    return city


def set_building_level(
    db: Session,
    city_id: int,
    building_type: str,
    new_level: int,
    admin_user: models.User,
    *,
    reason: str | None,
    support_case_id: int | None = None,
) -> models.Building:
    normalized_reason = _require_reason(reason)
    _validate_support_case(db, support_case_id)
    city = db.query(models.City).filter(models.City.id == city_id).with_for_update().one_or_none()
    if city is None:
        raise HTTPException(status_code=404, detail="City not found")
    building = (
        db.query(models.Building)
        .filter(models.Building.city_id == city.id, models.Building.name == building_type)
        .with_for_update()
        .one_or_none()
    )
    before = {"exists": building is not None, "level": building.level if building else None}
    if building is None:
        building = models.Building(city_id=city.id, name=building_type, level=new_level)
        db.add(building)
        db.flush()
    else:
        building.level = new_level
    after = {"exists": True, "level": building.level}
    log_action(
        db,
        admin_user.id,
        "set_building_level",
        {"city_id": city.id, "building_type": building_type},
        target_type="building",
        target_id=building.id,
        reason=normalized_reason,
        before_state=before,
        after_state=after,
        reversible=before != after,
        support_case_id=support_case_id,
    )
    db.commit()
    db.refresh(building)
    return building


def set_troop_amounts(
    db: Session,
    city_id: int,
    troop_amounts: Dict[str, int],
    admin_user: models.User,
    *,
    reason: str | None,
    support_case_id: int | None = None,
) -> list[models.Troop]:
    normalized_reason = _require_reason(reason)
    _validate_support_case(db, support_case_id)
    if not troop_amounts:
        raise HTTPException(status_code=400, detail="At least one troop update is required")
    city = db.query(models.City).filter(models.City.id == city_id).with_for_update().one_or_none()
    if city is None:
        raise HTTPException(status_code=404, detail="City not found")

    updated: list[models.Troop] = []
    before: Dict[str, Dict] = {}
    after: Dict[str, Dict] = {}
    for unit_type, quantity in troop_amounts.items():
        troop = (
            db.query(models.Troop)
            .filter(models.Troop.city_id == city.id, models.Troop.unit_type == unit_type)
            .with_for_update()
            .one_or_none()
        )
        before[unit_type] = {"exists": troop is not None, "quantity": troop.quantity if troop else None}
        if troop is None:
            troop = models.Troop(city_id=city.id, unit_type=unit_type, quantity=quantity)
            db.add(troop)
        else:
            troop.quantity = quantity
        updated.append(troop)
        after[unit_type] = {"exists": True, "quantity": quantity}
    db.flush()
    log_action(
        db,
        admin_user.id,
        "set_troop_amounts",
        {"city_id": city.id, "unit_types": sorted(troop_amounts)},
        target_type="city_troops",
        target_id=city.id,
        reason=normalized_reason,
        before_state=before,
        after_state=after,
        reversible=before != after,
        support_case_id=support_case_id,
    )
    db.commit()
    for troop in updated:
        db.refresh(troop)
    return updated


def create_city(
    db: Session,
    payload: Dict,
    admin_user: models.User,
    *,
    reason: str | None,
    support_case_id: int | None = None,
) -> models.City:
    normalized_reason = _require_reason(reason)
    _validate_support_case(db, support_case_id)
    owner = db.query(models.User).filter(models.User.id == payload["owner_id"]).one_or_none()
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    world = db.query(models.World).filter(models.World.id == payload["world_id"]).one_or_none()
    if world is None or getattr(world, "lifecycle_status", "open") != "open":
        raise HTTPException(status_code=404, detail="World not available")
    membership = (
        db.query(models.PlayerWorld)
        .filter(models.PlayerWorld.user_id == owner.id, models.PlayerWorld.world_id == world.id)
        .one_or_none()
    )
    if membership is None:
        raise HTTPException(status_code=400, detail="Owner has not joined this world")
    occupied = (
        db.query(models.City)
        .filter(models.City.world_id == world.id, models.City.x == payload.get("x", 0), models.City.y == payload.get("y", 0))
        .one_or_none()
    )
    if occupied is not None:
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
    db.flush()
    production.recalculate_resources(db, city, commit=False)
    log_action(
        db,
        admin_user.id,
        "create_city",
        {"city_id": city.id, "owner_id": owner.id, "world_id": world.id},
        target_type="city",
        target_id=city.id,
        reason=normalized_reason,
        before_state=None,
        after_state={"exists": True},
        reversible=False,
        support_case_id=support_case_id,
    )
    db.commit()
    db.refresh(city)
    return city


def teleport_city(
    db: Session,
    city_id: int,
    x: int,
    y: int,
    admin_user: models.User,
    *,
    reason: str | None,
    support_case_id: int | None = None,
) -> models.City:
    normalized_reason = _require_reason(reason)
    _validate_support_case(db, support_case_id)
    city = db.query(models.City).filter(models.City.id == city_id).with_for_update().one_or_none()
    if city is None:
        raise HTTPException(status_code=404, detail="City not found")
    occupied = (
        db.query(models.City)
        .filter(models.City.world_id == city.world_id, models.City.x == x, models.City.y == y, models.City.id != city.id)
        .one_or_none()
    )
    if occupied is not None:
        raise HTTPException(status_code=409, detail="Coordinates already occupied in this world")
    before = {"x": city.x, "y": city.y}
    city.x = x
    city.y = y
    after = {"x": city.x, "y": city.y}
    log_action(
        db,
        admin_user.id,
        "teleport_city",
        {"city_id": city.id},
        target_type="city_coordinates",
        target_id=city.id,
        reason=normalized_reason,
        before_state=before,
        after_state=after,
        reversible=before != after,
        support_case_id=support_case_id,
    )
    db.commit()
    db.refresh(city)
    return city


def _load_state(raw: str | None) -> Dict:
    return json.loads(raw) if raw else {}


def _ensure_current_matches(current: Dict, expected: Dict) -> None:
    if current != expected:
        raise HTTPException(status_code=409, detail="Target changed after the audited action")


def revert_action(
    db: Session,
    log_id: int,
    *,
    admin_user: models.User,
    reason: str | None,
) -> models.Log:
    normalized_reason = _require_reason(reason)
    original = db.query(models.Log).filter(models.Log.id == log_id).with_for_update().one_or_none()
    if original is None:
        raise HTTPException(status_code=404, detail="Audit action not found")
    if not original.reversible:
        raise HTTPException(status_code=409, detail="Audit action is not reversible")
    if original.reversed_at is not None:
        raise HTTPException(status_code=409, detail="Audit action already reverted")

    required_capability = {
        "update_city_resources": "game.correct",
        "teleport_city": "game.correct",
        "set_building_level": "game.correct",
        "set_troop_amounts": "game.correct",
        "set_user_freeze": "account.freeze",
        "moderate_chat_message": "content.moderate",
        "moderate_forum_post": "content.moderate",
    }.get(original.action)
    if required_capability is None:
        raise HTTPException(status_code=409, detail="Reversal handler is not available for this action")
    if not admin_permissions.has_capability(admin_user, required_capability):
        raise HTTPException(
            status_code=403,
            detail=f"Administrative capability required: {required_capability}",
        )

    before = _load_state(original.before_state)
    after = _load_state(original.after_state)

    if original.action == "update_city_resources":
        city = db.query(models.City).filter(models.City.id == original.target_id).with_for_update().one_or_none()
        if city is None:
            raise HTTPException(status_code=409, detail="Target no longer exists")
        _ensure_current_matches({key: getattr(city, key) for key in after}, after)
        for key, value in before.items():
            setattr(city, key, value)
    elif original.action == "teleport_city":
        city = db.query(models.City).filter(models.City.id == original.target_id).with_for_update().one_or_none()
        if city is None:
            raise HTTPException(status_code=409, detail="Target no longer exists")
        _ensure_current_matches({"x": city.x, "y": city.y}, after)
        occupied = (
            db.query(models.City)
            .filter(models.City.world_id == city.world_id, models.City.x == before["x"], models.City.y == before["y"], models.City.id != city.id)
            .one_or_none()
        )
        if occupied is not None:
            raise HTTPException(status_code=409, detail="Original coordinates are now occupied")
        city.x, city.y = before["x"], before["y"]
    elif original.action == "set_building_level":
        building = db.query(models.Building).filter(models.Building.id == original.target_id).with_for_update().one_or_none()
        if building is None:
            raise HTTPException(status_code=409, detail="Target no longer exists")
        _ensure_current_matches({"exists": True, "level": building.level}, after)
        if before.get("exists"):
            building.level = before["level"]
        else:
            db.delete(building)
    elif original.action == "set_troop_amounts":
        city_id = original.target_id
        current: Dict[str, Dict] = {}
        rows: Dict[str, models.Troop | None] = {}
        for unit_type, expected in after.items():
            troop = (
                db.query(models.Troop)
                .filter(models.Troop.city_id == city_id, models.Troop.unit_type == unit_type)
                .with_for_update()
                .one_or_none()
            )
            rows[unit_type] = troop
            current[unit_type] = {"exists": troop is not None, "quantity": troop.quantity if troop else None}
        _ensure_current_matches(current, after)
        for unit_type, state in before.items():
            troop = rows[unit_type]
            if state.get("exists"):
                troop.quantity = state["quantity"]
            elif troop is not None:
                db.delete(troop)
    elif original.action == "set_user_freeze":
        user = db.query(models.User).filter(models.User.id == original.target_id).with_for_update().one_or_none()
        if user is None:
            raise HTTPException(status_code=409, detail="Target no longer exists")
        current = {"is_frozen": bool(user.is_frozen), "freeze_reason": user.freeze_reason}
        _ensure_current_matches(current, after)
        user.is_frozen = bool(before["is_frozen"])
        user.freeze_reason = before.get("freeze_reason")
        user.auth_version += 1
    elif original.action in {"moderate_chat_message", "moderate_forum_post"}:
        from . import moderation

        moderation.revert_from_audit(db, original, before, after)
    else:
        raise HTTPException(status_code=409, detail="Reversal handler is not available for this action")

    from ..utils import utc_now

    original.reversed_at = utc_now()
    original.reversed_by_id = admin_user.id
    reversal = log_action(
        db,
        admin_user.id,
        "revert_admin_action",
        {"original_log_id": original.id},
        target_type=original.target_type,
        target_id=original.target_id,
        reason=normalized_reason,
        before_state=after,
        after_state=before,
        reversible=False,
        support_case_id=original.support_case_id,
    )
    db.commit()
    db.refresh(reversal)
    return reversal

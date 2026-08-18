"""Server-authoritative movement dispatch and worker-side resolution."""

from __future__ import annotations

import json
import logging
import math
from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..utils import utc_now
from . import anticheat, combat, espionage
from . import event as event_service
from . import notification as notification_service
from . import production
from . import quest as quest_service

logger = logging.getLogger(__name__)

UNIT_SPEED = {
    "basic_infantry": 0.6,
    "heavy_infantry": 0.55,
    "archer": 0.7,
    "fast_cavalry": 1.2,
    "heavy_cavalry": 0.9,
    "spy": 1.5,
    "ram": 0.5,
    "catapult": 0.45,
    "noble": 0.4,
}

PLAYER_MOVEMENT_TYPES = {"attack", "spy", "reinforce", "transport"}
RESOURCE_FIELDS = ("wood", "clay", "iron")


def calculate_distance(origin: models.City, target: models.City) -> float:
    return math.hypot(origin.x - target.x, origin.y - target.y)


def _normalize_troops(troops: Dict[str, int] | None) -> Dict[str, int]:
    normalized: Dict[str, int] = {}
    for unit, raw_amount in (troops or {}).items():
        if unit not in UNIT_SPEED:
            raise ValueError(f"Unknown troop type: {unit}")
        amount = int(raw_amount)
        if amount < 0:
            raise ValueError("Troop amounts cannot be negative")
        if amount > 0:
            normalized[unit] = amount
    return normalized


def _normalize_resources(resources: Dict[str, int] | None) -> Dict[str, int]:
    normalized: Dict[str, int] = {}
    for resource, raw_amount in (resources or {}).items():
        if resource not in RESOURCE_FIELDS:
            raise ValueError(f"Unknown resource: {resource}")
        amount = int(raw_amount)
        if amount < 0:
            raise ValueError("Resource amounts cannot be negative")
        if amount > 0:
            normalized[resource] = amount
    return normalized


def _get_base_speed(movement_type: str, troops: Dict[str, int]) -> float:
    if movement_type == "spy":
        return UNIT_SPEED["spy"]
    if movement_type == "transport":
        return 1.0
    speeds = [UNIT_SPEED[unit] for unit, amount in troops.items() if amount > 0]
    return min(speeds) if speeds else UNIT_SPEED["basic_infantry"]


def _validate_target_type(
    movement_type: str,
    target_city_id: int | None,
    target_oasis_id: int | None,
) -> None:
    if movement_type not in PLAYER_MOVEMENT_TYPES:
        raise ValueError(f"Unsupported movement type: {movement_type}")
    if (target_city_id is None) == (target_oasis_id is None):
        raise ValueError("Specify exactly one target")
    if movement_type in {"spy", "reinforce", "transport"} and target_city_id is None:
        raise ValueError(f"{movement_type} movements require a city target")


def _reserve_payload_and_create(
    db: Session,
    *,
    origin_city_id: int,
    target_city_id: int | None,
    target_oasis_id: int | None,
    movement_type: str,
    troops: Dict[str, int],
    resources: Dict[str, int],
    spy_count: int,
    arrival_time,
    speed: float,
    world_id: int,
    target_building: str | None,
) -> models.Movement:
    """Reserve the payload and create the movement under one city row lock."""

    city = (
        db.query(models.City)
        .filter(models.City.id == origin_city_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if city is None:
        raise ValueError("Origin city not found")

    reserved_troops = {"spy": spy_count} if movement_type == "spy" else troops
    if reserved_troops:
        rows = (
            db.query(models.Troop)
            .filter(
                models.Troop.city_id == city.id,
                models.Troop.unit_type.in_(list(reserved_troops)),
            )
            .with_for_update()
            .all()
        )
        by_type = {row.unit_type: row for row in rows}
        for unit, amount in reserved_troops.items():
            row = by_type.get(unit)
            if row is None or row.quantity < amount:
                raise ValueError(f"Not enough {unit}")
        for unit, amount in reserved_troops.items():
            by_type[unit].quantity -= amount
            db.add(by_type[unit])

    if movement_type == "transport":
        if not resources:
            raise ValueError("Transport requires resources")
        if not production.check_cost(city, resources):
            raise ValueError("Insufficient resources")
        production.pay_cost(city, resources)

    movement_obj = models.Movement(
        origin_city_id=city.id,
        target_city_id=target_city_id,
        target_oasis_id=target_oasis_id,
        movement_type=movement_type,
        troops=troops,
        resources=resources,
        spy_count=spy_count,
        arrival_time=arrival_time,
        speed_used=speed,
        world_id=world_id,
        target_building=target_building,
        status="ongoing",
    )
    db.add(movement_obj)
    db.commit()
    db.refresh(movement_obj)
    return movement_obj


def _run_dispatch_side_effects(
    db: Session,
    movement_obj: models.Movement,
    origin_city: models.City,
    target_city: models.City | None,
) -> None:
    """Run non-economic effects only after the movement transaction committed."""

    if movement_obj.movement_type == "attack" and target_city and target_city.owner:
        try:
            notification_service.create_notification(
                db,
                target_city.owner,
                title="¡Estás bajo ataque!",
                body=f"{origin_city.name} ha enviado tropas hacia tu ciudad {target_city.name}.",
                notification_type="attack_incoming",
            )
        except Exception:
            db.rollback()
            logger.exception("Failed to create incoming attack notification")

    event_type = {
        "attack": "attack_sent",
        "spy": "spy_sent",
    }.get(movement_obj.movement_type)
    if event_type and origin_city.owner:
        try:
            quest_service.handle_event(
                db,
                origin_city.owner,
                event_type,
                {"movement_id": movement_obj.id},
            )
        except Exception:
            db.rollback()
            logger.exception("Failed to update movement quest progress")


def send_movement(
    db: Session,
    origin_city: models.City,
    target_city_id: int | None,
    movement_type: str,
    troops: Dict[str, int] | None = None,
    resources: Dict[str, int] | None = None,
    spy_count: int = 0,
    target_city: models.City | None = None,
    target_building: str | None = None,
    target_oasis_id: int | None = None,
) -> models.Movement:
    """Validate, reserve and persist a player movement atomically."""

    _validate_target_type(movement_type, target_city_id, target_oasis_id)
    normalized_troops = _normalize_troops(troops)
    normalized_resources = _normalize_resources(resources)

    if target_city_id is not None:
        target_city = target_city or (
            db.query(models.City)
            .options(selectinload(models.City.owner))
            .filter(models.City.id == target_city_id)
            .first()
        )
        if not target_city:
            raise ValueError("Target city not found")
        if target_city.world_id != origin_city.world_id:
            raise ValueError("Target city is not in the same world")
        if target_city.id == origin_city.id:
            raise ValueError("Origin and target city must be different")
        target_x, target_y = target_city.x, target_city.y
    else:
        target_oasis = (
            db.query(models.Oasis)
            .filter(models.Oasis.id == target_oasis_id)
            .first()
        )
        if not target_oasis:
            raise ValueError("Target oasis not found")
        if target_oasis.world_id != origin_city.world_id:
            raise ValueError("Target oasis is not in the same world")
        target_x, target_y = target_oasis.x, target_oasis.y

    if movement_type in {"attack", "reinforce"} and not normalized_troops:
        raise ValueError(f"{movement_type} requires at least one troop")
    if movement_type == "spy":
        spy_count = int(spy_count)
        if spy_count <= 0:
            raise ValueError("Spy missions require at least one spy")
        normalized_troops = {}
    elif spy_count:
        raise ValueError("spy_count is only valid for spy missions")
    if movement_type != "transport" and normalized_resources:
        raise ValueError("Resources can only be sent with transport movements")

    base_speed = _get_base_speed(movement_type, normalized_troops)
    modifiers = event_service.get_active_modifiers(db, world_id=origin_city.world_id)
    effective_speed = base_speed * modifiers.get("movement_speed", 1.0)
    world_speed = origin_city.world.speed_modifier if origin_city.world else 1.0
    speed = max(effective_speed * world_speed, 0.01)
    distance = math.hypot(origin_city.x - target_x, origin_city.y - target_y)
    arrival_time = utc_now() + timedelta(hours=distance / speed)

    # Anti-cheat helpers currently own their commits. They therefore run before
    # any troops/resources are reserved so a helper failure cannot strand a
    # paid payload without a movement record.
    if origin_city.owner:
        anticheat.check_action_speed(db, origin_city.owner, "movement")
        if target_city is not None:
            anticheat.check_movement_legitimacy(
                db,
                origin_city,
                target_city,
                movement_type,
                arrival_time,
                speed,
                spy_count,
            )

    movement_obj = _reserve_payload_and_create(
        db,
        origin_city_id=origin_city.id,
        target_city_id=target_city_id,
        target_oasis_id=target_oasis_id,
        movement_type=movement_type,
        troops=normalized_troops,
        resources=normalized_resources,
        spy_count=spy_count,
        arrival_time=arrival_time,
        speed=speed,
        world_id=origin_city.world_id,
        target_building=target_building,
    )
    _run_dispatch_side_effects(db, movement_obj, origin_city, target_city)

    logger.info(
        "movement_created",
        extra={
            "movement_id": movement_obj.id,
            "origin_city_id": origin_city.id,
            "target_city_id": target_city_id,
            "target_oasis_id": target_oasis_id,
            "movement_type": movement_type,
            "arrival_time": arrival_time.isoformat(),
        },
    )
    return movement_obj


def _add_report(
    db: Session,
    *,
    city_id: int,
    world_id: int,
    report_type: str,
    content: str,
    attacker_city_id: int | None,
    defender_city_id: int | None,
) -> models.Report:
    report = models.Report(
        city_id=city_id,
        world_id=world_id,
        report_type=report_type,
        content=content,
        attacker_city_id=attacker_city_id,
        defender_city_id=defender_city_id,
    )
    db.add(report)
    return report


def _create_return_movement(
    db: Session,
    *,
    from_city: models.City,
    to_city: models.City,
    source_movement: models.Movement,
    troops: Dict[str, int] | None = None,
    resources: Dict[str, int] | None = None,
) -> models.Movement:
    speed = source_movement.speed_used or UNIT_SPEED["basic_infantry"]
    distance = calculate_distance(from_city, to_city)
    return_move = models.Movement(
        origin_city_id=from_city.id,
        target_city_id=to_city.id,
        movement_type="return",
        troops=troops or {},
        resources=resources or {},
        arrival_time=utc_now() + timedelta(hours=distance / max(speed, 0.01)),
        speed_used=speed,
        world_id=source_movement.world_id,
        status="ongoing",
    )
    db.add(return_move)
    return return_move


def _apply_hero_xp_without_commit(hero: models.Hero | None, xp_amount: int) -> None:
    if not hero or xp_amount <= 0:
        return
    from .hero import XP_TABLE

    hero.xp += int(xp_amount)
    while hero.level < 100 and hero.xp >= XP_TABLE[hero.level]:
        hero.xp -= XP_TABLE[hero.level]
        hero.level += 1


def _apply_defender_losses(defender: models.City, losses: Dict[str, int]) -> None:
    by_type = {troop.unit_type: troop for troop in defender.troops}
    for unit, loss in losses.items():
        troop = by_type.get(unit)
        if troop and loss > 0:
            troop.quantity = max(0, troop.quantity - int(loss))


def _resolve_attack_core(db: Session, movement: models.Movement) -> List[dict[str, Any]]:
    attacker = movement.origin_city
    defender = movement.target_city
    if not attacker or not defender:
        return []

    original_defender_owner_id = defender.owner_id
    attacker_resources_before = {
        resource: float(getattr(attacker, resource)) for resource in RESOURCE_FIELDS
    }
    modifiers = event_service.get_active_modifiers(db, world_id=movement.world_id)
    result = combat.resolve_battle(
        attacker,
        defender,
        movement.troops or {},
        modifiers,
        target_building=movement.target_building,
    )

    # Combat calculates loot and deducts it from the defender. The loot belongs
    # to the returning army, not to the city at impact time. Reset only the
    # attacker's immediate credit and carry the exact loot on the return march.
    for resource, before in attacker_resources_before.items():
        setattr(attacker, resource, before)

    _apply_defender_losses(defender, result.get("defender_losses", {}))
    if attacker.owner and attacker.owner.hero:
        _apply_hero_xp_without_commit(attacker.owner.hero, result.get("xp_gained", 0))

    content = combat.build_battle_report_content(attacker, defender, result)
    _add_report(
        db,
        city_id=attacker.id,
        world_id=movement.world_id,
        report_type="battle",
        content=content,
        attacker_city_id=attacker.id,
        defender_city_id=defender.id,
    )
    _add_report(
        db,
        city_id=defender.id,
        world_id=movement.world_id,
        report_type="battle",
        content=content,
        attacker_city_id=attacker.id,
        defender_city_id=defender.id,
    )

    survivors = {
        unit: int(amount)
        for unit, amount in result.get("attacker_survivors", {}).items()
        if int(amount) > 0
    }
    loot = {
        resource: int(result.get("loot", {}).get(resource, 0) or 0)
        for resource in RESOURCE_FIELDS
    }
    if survivors or any(loot.values()):
        _create_return_movement(
            db,
            from_city=defender,
            to_city=attacker,
            source_movement=movement,
            troops=survivors,
            resources=loot,
        )

    effects: List[dict[str, Any]] = []
    if attacker.owner_id:
        effects.append(
            {
                "type": "notification",
                "user_id": attacker.owner_id,
                "title": "Informe de batalla listo",
                "body": f"Tu ataque contra {defender.name} ha generado un informe.",
                "notification_type": "report_ready",
                "allow_email": False,
            }
        )
    if original_defender_owner_id:
        effects.append(
            {
                "type": "notification",
                "user_id": original_defender_owner_id,
                "title": "Has recibido un informe de batalla",
                "body": f"Tu ciudad {defender.name} ha sido atacada. Hay un nuevo informe disponible.",
                "notification_type": "report_ready",
                "allow_email": False,
            }
        )
    if attacker.owner_id and sum(result.get("defender_survivors", {}).values()) == 0:
        effects.append(
            {
                "type": "achievement",
                "user_id": attacker.owner_id,
                "requirement_type": "win_battles",
                "increment": 1,
            }
        )
    return effects


def _resolve_oasis_attack_core(
    db: Session, movement: models.Movement
) -> List[dict[str, Any]]:
    attacker = movement.origin_city
    oasis = movement.target_oasis
    if not attacker or not oasis:
        return []

    attacker_hero = attacker.owner.hero if attacker.owner else None
    modifiers = event_service.get_active_modifiers(db, world_id=movement.world_id)
    result = combat.resolve_oasis_battle(
        attacker,
        oasis,
        movement.troops or {},
        modifiers=modifiers,
        attacker_hero=attacker_hero,
    )

    oasis_troops = dict(oasis.troops or {})
    for unit, loss in result.get("defender_losses", {}).items():
        oasis_troops[unit] = max(0, oasis_troops.get(unit, 0) - int(loss))
    oasis.troops = oasis_troops

    effects: List[dict[str, Any]] = []
    conquered = bool(result.get("conquered") or result.get("conquest"))
    if conquered:
        oasis.owner_city_id = attacker.id
        oasis.troops = {}
        if attacker.owner_id:
            effects.append(
                {
                    "type": "notification",
                    "user_id": attacker.owner_id,
                    "title": "¡Oasis Conquistado!",
                    "body": f"Has conquistado un oasis en ({oasis.x}, {oasis.y}).",
                    "notification_type": "conquest",
                    "allow_email": True,
                }
            )

    _apply_hero_xp_without_commit(attacker_hero, result.get("xp_gained", 0))
    content = combat.build_oasis_report_content(attacker, oasis, result)
    _add_report(
        db,
        city_id=attacker.id,
        world_id=movement.world_id,
        report_type="battle",
        content=content,
        attacker_city_id=attacker.id,
        defender_city_id=None,
    )

    survivors = {
        unit: int(amount)
        for unit, amount in result.get("attacker_survivors", {}).items()
        if int(amount) > 0
    }
    if survivors:
        speed = movement.speed_used or UNIT_SPEED["basic_infantry"]
        distance = math.hypot(attacker.x - oasis.x, attacker.y - oasis.y)
        db.add(
            models.Movement(
                origin_city_id=attacker.id,
                target_city_id=attacker.id,
                movement_type="return",
                troops=survivors,
                resources={},
                arrival_time=utc_now() + timedelta(hours=distance / max(speed, 0.01)),
                speed_used=speed,
                world_id=movement.world_id,
                status="ongoing",
            )
        )
    return effects


def _resolve_spy_core(db: Session, movement: models.Movement) -> List[dict[str, Any]]:
    if not movement.origin_city or not movement.target_city:
        return []
    _, _, surviving_spies, success_chance, success = espionage.resolve_spy(db, movement)
    if surviving_spies > 0:
        _create_return_movement(
            db,
            from_city=movement.target_city,
            to_city=movement.origin_city,
            source_movement=movement,
            troops={"spy": surviving_spies},
        )
    if movement.origin_city.owner_id:
        return [
            {
                "type": "spy_audit",
                "user_id": movement.origin_city.owner_id,
                "success_chance": success_chance,
                "success": success,
            }
        ]
    return []


def _credit_resources_with_storage(city: models.City, resources: Dict[str, int]) -> None:
    limit = production.get_storage_limit(city)
    for resource in RESOURCE_FIELDS:
        amount = max(int(resources.get(resource, 0) or 0), 0)
        current = float(getattr(city, resource))
        if current < limit and amount > 0:
            setattr(city, resource, min(current + amount, limit))


def _resolve_return_core(db: Session, movement: models.Movement) -> None:
    city = movement.target_city
    if not city:
        return

    for unit, raw_amount in (movement.troops or {}).items():
        amount = int(raw_amount)
        if amount <= 0:
            continue
        troop = (
            db.query(models.Troop)
            .filter(
                models.Troop.city_id == city.id,
                models.Troop.unit_type == unit,
            )
            .first()
        )
        if not troop:
            troop = models.Troop(city_id=city.id, unit_type=unit, quantity=0)
            db.add(troop)
        troop.quantity += amount

    _credit_resources_with_storage(city, movement.resources or {})
    from_city = movement.origin_city or city
    content = json.dumps(
        {
            "type": "return",
            "from": {"id": from_city.id, "name": from_city.name},
            "troops": movement.troops or {},
            "resources": movement.resources or {},
        }
    )
    _add_report(
        db,
        city_id=city.id,
        world_id=movement.world_id,
        report_type="return",
        content=content,
        attacker_city_id=from_city.id,
        defender_city_id=city.id,
    )


def _resolve_reinforce_core(db: Session, movement: models.Movement) -> None:
    receiver = movement.target_city
    sender = movement.origin_city
    if not receiver or not sender:
        return
    for unit, raw_amount in (movement.troops or {}).items():
        amount = int(raw_amount)
        if amount <= 0:
            continue
        troop = (
            db.query(models.Troop)
            .filter(
                models.Troop.city_id == receiver.id,
                models.Troop.unit_type == unit,
            )
            .first()
        )
        if not troop:
            troop = models.Troop(city_id=receiver.id, unit_type=unit, quantity=0)
            db.add(troop)
        troop.quantity += amount

    content = json.dumps(
        {
            "type": "reinforce",
            "sender": {"id": sender.id, "name": sender.name},
            "receiver": {"id": receiver.id, "name": receiver.name},
            "troops": movement.troops or {},
        }
    )
    for city_id in {sender.id, receiver.id}:
        _add_report(
            db,
            city_id=city_id,
            world_id=movement.world_id,
            report_type="reinforce",
            content=content,
            attacker_city_id=sender.id,
            defender_city_id=receiver.id,
        )


def _resolve_transport_core(
    db: Session, movement: models.Movement
) -> List[dict[str, Any]]:
    receiver = movement.target_city
    sender = movement.origin_city
    if not receiver or not sender:
        return []
    _credit_resources_with_storage(receiver, movement.resources or {})

    content = json.dumps(
        {
            "type": "trade",
            "sender": {"id": sender.id, "name": sender.name},
            "receiver": {"id": receiver.id, "name": receiver.name},
            "resources": movement.resources or {},
        }
    )
    for city_id in {sender.id, receiver.id}:
        _add_report(
            db,
            city_id=city_id,
            world_id=movement.world_id,
            report_type="trade",
            content=content,
            attacker_city_id=sender.id,
            defender_city_id=receiver.id,
        )

    speed = movement.speed_used or 1.0
    db.add(
        models.Movement(
            origin_city_id=receiver.id,
            target_city_id=sender.id,
            movement_type="transport_return",
            troops={},
            resources={},
            arrival_time=utc_now()
            + timedelta(hours=calculate_distance(receiver, sender) / max(speed, 0.01)),
            speed_used=speed,
            world_id=movement.world_id,
            status="ongoing",
        )
    )
    if receiver.owner_id:
        return [
            {
                "type": "notification",
                "user_id": receiver.owner_id,
                "title": "Recursos recibidos",
                "body": f"Has recibido recursos de {sender.name}.",
                "notification_type": "transport_received",
                "allow_email": True,
            }
        ]
    return []


def _run_resolution_effect(db: Session, effect: dict[str, Any]) -> None:
    effect_type = effect["type"]
    if effect_type == "notification":
        user = db.query(models.User).filter(models.User.id == effect["user_id"]).first()
        if user:
            notification_service.create_notification(
                db,
                user,
                title=effect["title"],
                body=effect["body"],
                notification_type=effect["notification_type"],
                allow_email=effect.get("allow_email", True),
            )
    elif effect_type == "achievement":
        from .achievement import update_achievement_progress

        update_achievement_progress(
            db,
            effect["user_id"],
            effect["requirement_type"],
            increment=effect.get("increment"),
        )
    elif effect_type == "spy_audit":
        user = db.query(models.User).filter(models.User.id == effect["user_id"]).first()
        if user:
            anticheat.check_spy_result(
                db,
                user,
                effect["success_chance"],
                effect["success"],
            )


def resolve_due_movements(db: Session) -> List[models.Movement]:
    """Resolve each due movement exactly once inside the worker transaction."""

    now = utc_now()
    movements = (
        db.query(models.Movement)
        .options(
            selectinload(models.Movement.origin_city).selectinload(models.City.owner),
            selectinload(models.Movement.origin_city).selectinload(models.City.buildings),
            selectinload(models.Movement.target_city).selectinload(models.City.owner),
            selectinload(models.Movement.target_city).selectinload(models.City.troops),
            selectinload(models.Movement.target_city).selectinload(models.City.buildings),
            selectinload(models.Movement.target_oasis),
        )
        .filter(
            models.Movement.arrival_time <= now,
            models.Movement.status == "ongoing",
        )
        .order_by(models.Movement.id.asc())
        .with_for_update(skip_locked=True)
        .all()
    )
    if not movements:
        return []

    effects: List[dict[str, Any]] = []
    for movement in movements:
        if movement.movement_type == "spy":
            effects.extend(_resolve_spy_core(db, movement))
        elif movement.movement_type == "attack":
            if movement.target_oasis_id is not None:
                effects.extend(_resolve_oasis_attack_core(db, movement))
            else:
                effects.extend(_resolve_attack_core(db, movement))
        elif movement.movement_type == "reinforce":
            _resolve_reinforce_core(db, movement)
        elif movement.movement_type == "transport":
            effects.extend(_resolve_transport_core(db, movement))
        elif movement.movement_type == "return":
            _resolve_return_core(db, movement)
        elif movement.movement_type == "transport_return":
            if movement.target_city and movement.target_city.owner_id:
                effects.append(
                    {
                        "type": "notification",
                        "user_id": movement.target_city.owner_id,
                        "title": "Comerciantes regresaron",
                        "body": "Tus comerciantes han regresado.",
                        "notification_type": "transport_return",
                        "allow_email": False,
                    }
                )

        # Mark completed before any helper that is allowed to commit. All core
        # state, reports, losses and return marches commit together below.
        movement.status = "completed"
        db.add(movement)

    db.commit()

    for effect in effects:
        try:
            _run_resolution_effect(db, effect)
        except Exception:
            db.rollback()
            logger.exception(
                "Post-resolution side effect failed",
                extra={"effect_type": effect.get("type")},
            )

    logger.info(
        "movements_resolved",
        extra={"movement_ids": [movement.id for movement in movements]},
    )
    return movements


# Compatibility entrypoints kept for old callers. They now share the single
# canonical resolver instead of maintaining separate combat implementations.
def process_movements(db: Session) -> List[models.Movement]:
    return resolve_due_movements(db)


def process_arrived_movements(db: Session) -> List[models.Movement]:
    return resolve_due_movements(db)

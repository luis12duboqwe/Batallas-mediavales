from __future__ import annotations

import json
import logging
import math
from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..utils import utc_now
from . import anticheat, balance, combat, espionage, hero_rules
from . import event as event_service
from . import notification as notification_service
from . import production
from . import quest as quest_service

logger = logging.getLogger(__name__)

UNIT_SPEED = balance.UNIT_SPEED
PLAYER_MOVEMENT_TYPES = {"attack", "spy", "reinforce"}
RESOURCE_FIELDS = balance.RESOURCE_FIELDS


def calculate_distance(city1: models.City, city2: models.City) -> float:
    return math.hypot(city1.x - city2.x, city1.y - city2.y)


def _normalize_troops(troops: Dict[str, int] | None) -> Dict[str, int]:
    normalized: Dict[str, int] = {}
    for unit, raw_amount in (troops or {}).items():
        canonical = balance.LEGACY_UNIT_ALIASES.get(unit, unit)
        if canonical not in balance.UNIT_CATALOG:
            raise ValueError(f"Unknown unit type: {unit}")
        amount = int(raw_amount)
        if amount < 0:
            raise ValueError("Troop quantities cannot be negative")
        if amount > 0:
            normalized[canonical] = normalized.get(canonical, 0) + amount
    return normalized


def _normalize_resources(resources: Dict[str, int] | None) -> Dict[str, int]:
    unknown = set(resources or {}) - set(RESOURCE_FIELDS)
    if unknown:
        raise ValueError(f"Unknown resource type: {sorted(unknown)[0]}")
    normalized: Dict[str, int] = {}
    for resource in RESOURCE_FIELDS:
        amount = int((resources or {}).get(resource, 0))
        if amount < 0:
            raise ValueError("Resource quantities cannot be negative")
        if amount > 0:
            normalized[resource] = amount
    return normalized


def _get_base_speed(movement_type: str, troops: Dict[str, int]) -> float:
    if movement_type == "spy":
        return UNIT_SPEED["spy"]
    if not troops:
        return UNIT_SPEED["basic_infantry"]
    return min(UNIT_SPEED[unit] for unit in troops)


def _validate_target_type(
    movement_type: str,
    target_city_id: int | None,
    target_oasis_id: int | None,
) -> None:
    if movement_type not in PLAYER_MOVEMENT_TYPES:
        if movement_type == "transport":
            raise ValueError("Transport movements must be created through the market service")
        raise ValueError(f"Unsupported movement type: {movement_type}")
    if (target_city_id is None) == (target_oasis_id is None):
        raise ValueError("Specify exactly one target")
    if movement_type in {"spy", "reinforce"} and target_city_id is None:
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
    base_speed: float,
    movement_speed_multiplier: float,
    world_speed: float,
    distance: float,
    world_id: int,
    target_building: str | None,
    hero_id: int | None,
) -> models.Movement:
    """Reserve troops/hero and freeze authoritative travel timing atomically."""

    city = (
        db.query(models.City)
        .filter(models.City.id == origin_city_id)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if city is None:
        raise ValueError("Origin city not found")

    locked_hero = None
    if hero_id is not None:
        if movement_type != "attack":
            raise ValueError("Hero can only be assigned to attack movements")
        locked_hero = (
            db.query(models.Hero)
            .filter(
                models.Hero.id == hero_id,
                models.Hero.user_id == city.owner_id,
                models.Hero.world_id == world_id,
                models.Hero.city_id == city.id,
            )
            .with_for_update()
            .populate_existing()
            .one_or_none()
        )
        if locked_hero is None:
            raise ValueError("Hero does not belong to the origin city and world")
        if locked_hero.status != "home":
            raise ValueError("Hero is busy")
        if float(locked_hero.health) <= 0:
            raise ValueError("Hero is dead")

    hero_speed_bonus = hero_rules.speed_bonus(locked_hero) if locked_hero else 0.0
    speed = max(
        float(base_speed)
        * max(float(movement_speed_multiplier), 0.0)
        * max(float(world_speed), 0.0)
        * (1.0 + hero_speed_bonus),
        0.01,
    )
    arrival_time = utc_now() + timedelta(hours=max(float(distance), 0.0) / speed)

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
        raise ValueError("Transport movements must be created through the market service")

    if locked_hero is not None:
        locked_hero.status = "moving"
        db.add(locked_hero)

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
        hero_id=hero_id,
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

    event_type = {"attack": "attack_sent", "spy": "spy_sent"}.get(movement_obj.movement_type)
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
    hero_id: int | None = None,
) -> models.Movement:
    """Validate, reserve and persist a player movement atomically."""

    _validate_target_type(movement_type, target_city_id, target_oasis_id)
    normalized_troops = _normalize_troops(troops)
    normalized_resources = _normalize_resources(resources)
    if hero_id is not None and movement_type != "attack":
        raise ValueError("Hero can only be assigned to attack movements")

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
        target_oasis = db.query(models.Oasis).filter(models.Oasis.id == target_oasis_id).first()
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
    if normalized_resources:
        raise ValueError("Resources can only be sent through the market service")

    base_speed = _get_base_speed(movement_type, normalized_troops)
    modifiers = event_service.get_active_modifiers(db, world_id=origin_city.world_id)
    movement_speed_multiplier = float(modifiers.get("movement_speed", 1.0))
    world_speed = float(origin_city.world.speed_modifier if origin_city.world else 1.0)
    distance = math.hypot(origin_city.x - target_x, origin_city.y - target_y)

    if origin_city.owner:
        anticheat.check_action_speed(db, origin_city.owner, "movement")

    movement_obj = _reserve_payload_and_create(
        db,
        origin_city_id=origin_city.id,
        target_city_id=target_city_id,
        target_oasis_id=target_oasis_id,
        movement_type=movement_type,
        troops=normalized_troops,
        resources=normalized_resources,
        spy_count=spy_count,
        base_speed=base_speed,
        movement_speed_multiplier=movement_speed_multiplier,
        world_speed=world_speed,
        distance=distance,
        world_id=origin_city.world_id,
        target_building=target_building,
        hero_id=hero_id,
    )

    if origin_city.owner and target_city is not None:
        anticheat.check_movement_legitimacy(
            db,
            origin_city,
            target_city,
            movement_type,
            movement_obj.arrival_time,
            float(movement_obj.speed_used or 0.01),
            spy_count,
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
            "hero_id": hero_id,
            "arrival_time": movement_obj.arrival_time.isoformat(),
            "speed_used": movement_obj.speed_used,
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
    attacker_city_id: int | None = None,
    defender_city_id: int | None = None,
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
        hero_id=source_movement.hero_id,
        arrival_time=utc_now() + timedelta(hours=distance / max(speed, 0.01)),
        speed_used=speed,
        world_id=source_movement.world_id,
        status="ongoing",
    )
    db.add(return_move)
    return return_move


def _hero_for_world(owner: models.User | None, world_id: int) -> models.Hero | None:
    if owner is None:
        return None
    return owner.hero_for_world(world_id)


def _apply_hero_xp_without_commit(hero: models.Hero | None, xp_amount: int) -> None:
    """Add XP and normalize all earned levels without committing the worker txn."""

    if hero is None:
        return
    amount = int(xp_amount)
    if amount < 0:
        raise ValueError("Hero XP cannot be negative")
    from .hero import XP_TABLE

    hero.xp += amount
    while hero.level < hero_rules.HERO_MAX_LEVEL and hero.xp >= XP_TABLE[hero.level]:
        hero.xp -= XP_TABLE[hero.level]
        hero.level += 1


def _apply_defender_losses(defender: models.City, losses: Dict[str, int]) -> None:
    by_type = {troop.unit_type: troop for troop in defender.troops}
    for unit, loss in losses.items():
        troop = by_type.get(unit)
        if troop and loss > 0:
            troop.quantity = max(0, troop.quantity - int(loss))


def _movement_hero(movement: models.Movement) -> models.Hero | None:
    hero = movement.hero
    if hero is None or hero.world_id != movement.world_id or hero.status != "moving" or hero.health <= 0:
        return None
    return hero


def _resolve_attack_core(db: Session, movement: models.Movement) -> List[dict[str, Any]]:
    attacker = movement.origin_city
    defender = movement.target_city
    if not attacker or not defender:
        return []

    attacker_hero = _movement_hero(movement)
    defender_hero = _hero_for_world(defender.owner, movement.world_id)
    if defender_hero and (defender_hero.city_id != defender.id or defender_hero.status != "home"):
        defender_hero = None

    original_defender_owner_id = defender.owner_id
    attacker_resources_before = {resource: float(getattr(attacker, resource)) for resource in RESOURCE_FIELDS}
    modifiers = event_service.get_active_modifiers(db, world_id=movement.world_id)
    result = combat.resolve_battle(
        attacker,
        defender,
        movement.troops or {},
        modifiers,
        attacker_hero=attacker_hero,
        defender_hero=defender_hero,
        target_building=movement.target_building,
    )

    for resource, before in attacker_resources_before.items():
        setattr(attacker, resource, before)

    _apply_defender_losses(defender, result.get("defender_losses", {}))
    _apply_hero_xp_without_commit(attacker_hero, result.get("xp_gained", 0))
    # The BM-0064 combat engine already credits defender XP from attacker
    # casualties. Normalize that accumulated XP through the same BM-0068 level
    # table before this resolution transaction commits.
    _apply_hero_xp_without_commit(defender_hero, 0)

    content = combat.build_battle_report_content(attacker, defender, result)
    _add_report(db, city_id=attacker.id, world_id=movement.world_id, report_type="battle", content=content, attacker_city_id=attacker.id, defender_city_id=defender.id)
    _add_report(db, city_id=defender.id, world_id=movement.world_id, report_type="battle", content=content, attacker_city_id=attacker.id, defender_city_id=defender.id)

    survivors = {unit: int(amount) for unit, amount in result.get("attacker_survivors", {}).items() if int(amount) > 0}
    loot = {resource: int(result.get("loot", {}).get(resource, 0) or 0) for resource in RESOURCE_FIELDS}
    hero_returns = bool(attacker_hero and attacker_hero.status != "dead" and attacker_hero.health > 0)
    if survivors or any(loot.values()) or hero_returns:
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
        effects.append({"type": "notification", "user_id": attacker.owner_id, "title": "Informe de batalla listo", "body": f"Tu ataque contra {defender.name} ha generado un informe.", "notification_type": "report_ready", "allow_email": False})
    if original_defender_owner_id:
        effects.append({"type": "notification", "user_id": original_defender_owner_id, "title": "Has recibido un informe de batalla", "body": f"Tu ciudad {defender.name} ha sido atacada. Hay un nuevo informe disponible.", "notification_type": "report_ready", "allow_email": False})
    if attacker.owner_id and sum(result.get("defender_survivors", {}).values()) == 0:
        effects.append({"type": "achievement", "user_id": attacker.owner_id, "requirement_type": "win_battles", "increment": 1})
    return effects


def _resolve_oasis_attack_core(db: Session, movement: models.Movement) -> List[dict[str, Any]]:
    attacker = movement.origin_city
    oasis = movement.target_oasis
    if not attacker or not oasis:
        return []

    attacker_hero = _movement_hero(movement)
    modifiers = event_service.get_active_modifiers(db, world_id=movement.world_id)
    result = combat.resolve_oasis_battle(attacker, oasis, movement.troops or {}, modifiers=modifiers, attacker_hero=attacker_hero)

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
            effects.append({"type": "notification", "user_id": attacker.owner_id, "title": "¡Oasis Conquistado!", "body": f"Has conquistado un oasis en ({oasis.x}, {oasis.y}).", "notification_type": "conquest", "allow_email": True})

    _apply_hero_xp_without_commit(attacker_hero, result.get("xp_gained", 0))
    content = combat.build_oasis_report_content(attacker, oasis, result)
    _add_report(db, city_id=attacker.id, world_id=movement.world_id, report_type="battle", content=content, attacker_city_id=attacker.id, defender_city_id=None)

    survivors = {unit: int(amount) for unit, amount in result.get("attacker_survivors", {}).items() if int(amount) > 0}
    hero_returns = bool(attacker_hero and attacker_hero.status != "dead" and attacker_hero.health > 0)
    if survivors or hero_returns:
        speed = movement.speed_used or UNIT_SPEED["basic_infantry"]
        distance = math.hypot(attacker.x - oasis.x, attacker.y - oasis.y)
        db.add(models.Movement(
            origin_city_id=attacker.id,
            target_city_id=attacker.id,
            movement_type="return",
            troops=survivors,
            resources={},
            hero_id=movement.hero_id if hero_returns else None,
            arrival_time=utc_now() + timedelta(hours=distance / max(speed, 0.01)),
            speed_used=speed,
            world_id=movement.world_id,
            status="ongoing",
        ))
    return effects


def _resolve_spy_core(db: Session, movement: models.Movement) -> List[dict[str, Any]]:
    if not movement.origin_city or not movement.target_city:
        return []
    attacker_report, _, surviving_spies = espionage.resolve_spy(db, movement)
    report_data = json.loads(attacker_report.content)
    success_chance = float(report_data.get("success_chance", 0.0))
    success = bool(report_data.get("success", False))
    if surviving_spies > 0:
        _create_return_movement(db, from_city=movement.target_city, to_city=movement.origin_city, source_movement=movement, troops={"spy": surviving_spies})
    if movement.origin_city.owner_id:
        return [{"type": "spy_audit", "user_id": movement.origin_city.owner_id, "success_chance": success_chance, "success": success}]
    return []


def _credit_resources_with_storage(city: models.City, resources: Dict[str, int]) -> None:
    storage_limit = production.get_storage_limit(city)
    for resource, amount in resources.items():
        if resource not in RESOURCE_FIELDS:
            continue
        current = float(getattr(city, resource))
        setattr(city, resource, min(storage_limit, current + int(amount)))


def _resolve_return_core(db: Session, movement: models.Movement) -> None:
    city = movement.target_city or movement.origin_city
    if not city:
        return
    for unit, raw_amount in (movement.troops or {}).items():
        amount = int(raw_amount)
        if amount <= 0:
            continue
        troop = db.query(models.Troop).filter(models.Troop.city_id == city.id, models.Troop.unit_type == unit).first()
        if not troop:
            troop = models.Troop(city_id=city.id, unit_type=unit, quantity=0)
            db.add(troop)
        troop.quantity += amount

    _credit_resources_with_storage(city, movement.resources or {})
    if movement.hero_id is not None:
        hero = (
            db.query(models.Hero)
            .filter(
                models.Hero.id == movement.hero_id,
                models.Hero.world_id == movement.world_id,
                models.Hero.city_id == city.id,
            )
            .with_for_update()
            .populate_existing()
            .one_or_none()
        )
        if hero and hero.status != "dead" and hero.health > 0:
            hero.status = "home"
            db.add(hero)

    from_city = movement.origin_city or city
    content = json.dumps({"type": "return", "from": {"id": from_city.id, "name": from_city.name}, "troops": movement.troops or {}, "resources": movement.resources or {}, "hero_id": movement.hero_id})
    _add_report(db, city_id=city.id, world_id=movement.world_id, report_type="return", content=content, attacker_city_id=from_city.id, defender_city_id=city.id)


def _resolve_reinforce_core(db: Session, movement: models.Movement) -> None:
    sender = movement.origin_city
    receiver = movement.target_city
    if not sender or not receiver:
        return
    for unit, raw_amount in (movement.troops or {}).items():
        amount = int(raw_amount)
        if amount <= 0:
            continue
        troop = db.query(models.Troop).filter(models.Troop.city_id == receiver.id, models.Troop.unit_type == unit).first()
        if not troop:
            troop = models.Troop(city_id=receiver.id, unit_type=unit, quantity=0)
            db.add(troop)
        troop.quantity += amount

    content = json.dumps({"type": "reinforce", "sender": {"id": sender.id, "name": sender.name}, "receiver": {"id": receiver.id, "name": receiver.name}, "troops": movement.troops or {}})
    for city_id in {sender.id, receiver.id}:
        _add_report(db, city_id=city_id, world_id=movement.world_id, report_type="reinforce", content=content, attacker_city_id=sender.id, defender_city_id=receiver.id)


def _canonical_transport_resources(resources: Dict[str, int] | None) -> Dict[str, int]:
    return {resource: max(int((resources or {}).get(resource, 0) or 0), 0) for resource in RESOURCE_FIELDS if int((resources or {}).get(resource, 0) or 0) > 0}


def _lock_city_for_delivery(db: Session, city_id: int) -> models.City | None:
    return db.query(models.City).filter(models.City.id == city_id).with_for_update().populate_existing().one_or_none()


def _lock_transport_cities(db: Session, *city_ids: int | None) -> dict[int, models.City]:
    locked: dict[int, models.City] = {}
    for city_id in sorted({int(value) for value in city_ids if value is not None}):
        city = _lock_city_for_delivery(db, city_id)
        if city is not None:
            locked[city_id] = city
    return locked


def _can_store_all(city: models.City, resources: Dict[str, int]) -> bool:
    limit = float(production.get_storage_limit(city))
    return all(float(getattr(city, resource)) + int(amount) <= limit for resource, amount in resources.items())


def _credit_resources_exact(city: models.City, resources: Dict[str, int]) -> None:
    for resource, amount in resources.items():
        setattr(city, resource, float(getattr(city, resource)) + int(amount))


def _resolve_transport_core(db: Session, movement: models.Movement) -> List[dict[str, Any]]:
    sender_id = movement.origin_city_id
    receiver_id = movement.target_city_id
    if sender_id is None or receiver_id is None:
        return []
    locked_cities = _lock_transport_cities(db, sender_id, receiver_id)
    sender = locked_cities.get(sender_id)
    receiver = locked_cities.get(receiver_id)
    if sender is None or receiver is None:
        return []

    payload = _canonical_transport_resources(movement.resources)
    merchant_capacity = int((movement.resources or {}).get("capacity", 0) or 0)
    delivered = _can_store_all(receiver, payload)
    if delivered:
        _credit_resources_exact(receiver, payload)

    content = json.dumps({"type": "trade", "sender": {"id": sender.id, "name": sender.name}, "receiver": {"id": receiver.id, "name": receiver.name}, "resources": payload, "delivered": delivered, "return_reason": None if delivered else "insufficient_storage"})
    for city_id in {sender.id, receiver.id}:
        _add_report(db, city_id=city_id, world_id=movement.world_id, report_type="trade", content=content, attacker_city_id=sender.id, defender_city_id=receiver.id)

    speed = movement.speed_used or balance.TRANSPORT_BASE_SPEED
    return_resources: Dict[str, int] = {"capacity": merchant_capacity}
    if not delivered:
        return_resources.update(payload)
    db.add(models.Movement(
        origin_city_id=receiver.id,
        target_city_id=sender.id,
        movement_type="transport_return",
        troops={},
        resources=return_resources,
        arrival_time=utc_now() + timedelta(hours=calculate_distance(receiver, sender) / max(speed, 0.01)),
        speed_used=speed,
        world_id=movement.world_id,
        status="ongoing",
    ))

    effects: List[dict[str, Any]] = []
    if receiver.owner_id:
        effects.append({"type": "notification", "user_id": receiver.owner_id, "title": "Recursos recibidos" if delivered else "Transporte rechazado", "body": f"Has recibido recursos de {sender.name}." if delivered else "No había espacio suficiente para recibir el envío completo.", "notification_type": "transport_received" if delivered else "transport_rejected", "allow_email": True})
    if not delivered and sender.owner_id:
        effects.append({"type": "notification", "user_id": sender.owner_id, "title": "Recursos de regreso", "body": f"{receiver.name} no tenía espacio; el envío completo está regresando.", "notification_type": "transport_returning_resources", "allow_email": False})
    return effects


def _resolve_transport_return_core(db: Session, movement: models.Movement) -> tuple[bool, List[dict[str, Any]]]:
    target_city_id = movement.target_city_id
    if target_city_id is None:
        return True, []
    locked_cities = _lock_transport_cities(db, movement.origin_city_id, target_city_id)
    city = locked_cities.get(target_city_id)
    if city is None:
        return True, []

    payload = _canonical_transport_resources(movement.resources)
    if payload and not _can_store_all(city, payload):
        return False, []
    if payload:
        _credit_resources_exact(city, payload)
        content = json.dumps({"type": "transport_return", "resources": payload, "reason": "insufficient_destination_storage"})
        _add_report(db, city_id=city.id, world_id=movement.world_id, report_type="trade", content=content, attacker_city_id=movement.origin_city_id, defender_city_id=city.id)

    if not city.owner_id:
        return True, []
    return True, [{"type": "notification", "user_id": city.owner_id, "title": "Comerciantes regresaron", "body": "Tus comerciantes regresaron con el envío rechazado." if payload else "Tus comerciantes han regresado.", "notification_type": "transport_return", "allow_email": False}]


def _run_resolution_effect(db: Session, effect: dict[str, Any]) -> None:
    effect_type = effect["type"]
    if effect_type == "notification":
        user = db.query(models.User).filter(models.User.id == effect["user_id"]).first()
        if user:
            notification_service.create_notification(db, user, title=effect["title"], body=effect["body"], notification_type=effect["notification_type"], allow_email=effect.get("allow_email", True))
    elif effect_type == "achievement":
        from .achievement import update_achievement_progress
        update_achievement_progress(db, effect["user_id"], effect["requirement_type"], increment=effect.get("increment"))
    elif effect_type == "spy_audit":
        user = db.query(models.User).filter(models.User.id == effect["user_id"]).first()
        if user:
            anticheat.check_spy_result(db, user, effect["success_chance"], effect["success"])


def resolve_due_movements(db: Session) -> List[models.Movement]:
    now = utc_now()
    movements = (
        db.query(models.Movement)
        .options(
            selectinload(models.Movement.hero).selectinload(models.Hero.items).selectinload(models.HeroItem.template),
            selectinload(models.Movement.origin_city).selectinload(models.City.owner),
            selectinload(models.Movement.origin_city).selectinload(models.City.buildings),
            selectinload(models.Movement.target_city).selectinload(models.City.owner).selectinload(models.User.heroes).selectinload(models.Hero.items).selectinload(models.HeroItem.template),
            selectinload(models.Movement.target_city).selectinload(models.City.troops),
            selectinload(models.Movement.target_city).selectinload(models.City.buildings),
            selectinload(models.Movement.target_oasis),
        )
        .filter(models.Movement.arrival_time <= now, models.Movement.status == "ongoing")
        .order_by(models.Movement.id.asc())
        .with_for_update(skip_locked=True)
        .all()
    )

    effects: List[dict[str, Any]] = []
    for movement in movements:
        should_complete = True
        if movement.movement_type == "attack" and movement.target_oasis_id is not None:
            effects.extend(_resolve_oasis_attack_core(db, movement))
        elif movement.movement_type == "attack":
            effects.extend(_resolve_attack_core(db, movement))
        elif movement.movement_type == "spy":
            effects.extend(_resolve_spy_core(db, movement))
        elif movement.movement_type == "reinforce":
            _resolve_reinforce_core(db, movement)
        elif movement.movement_type == "return":
            _resolve_return_core(db, movement)
        elif movement.movement_type == "transport":
            effects.extend(_resolve_transport_core(db, movement))
        elif movement.movement_type == "transport_return":
            should_complete, return_effects = _resolve_transport_return_core(db, movement)
            effects.extend(return_effects)

        if should_complete:
            movement.status = "completed"
        db.add(movement)

    db.commit()

    for effect in effects:
        try:
            _run_resolution_effect(db, effect)
        except Exception:
            db.rollback()
            logger.exception("Post-resolution side effect failed", extra={"effect_type": effect.get("type")})

    logger.info("movements_resolved", extra={"movement_ids": [movement.id for movement in movements]})
    return movements


def process_movements(db: Session) -> List[models.Movement]:
    return resolve_due_movements(db)


def process_arrived_movements(db: Session) -> List[models.Movement]:
    return resolve_due_movements(db)
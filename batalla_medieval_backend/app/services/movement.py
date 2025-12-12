"""Movement orchestration including marching, arrivals, and combat."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy.orm import Session, selectinload

from .. import models
from ..utils import utc_now
from . import anticheat, combat, espionage
from . import event as event_service
from . import notification as notification_service
from . import report as report_service
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
}


def calculate_distance(origin: models.City, target: models.City) -> float:
    """Compute Euclidean distance between two cities."""

    return math.hypot(origin.x - target.x, origin.y - target.y)


def _get_base_speed(movement_type: str) -> float:
    """Return base unit speed used for travel time calculations."""

    if movement_type == "spy":
        return UNIT_SPEED.get("fast_cavalry", UNIT_SPEED["basic_infantry"])
    return UNIT_SPEED.get("basic_infantry", 0.6)


def _prepare_spy_mission(db: Session, origin_city: models.City, spy_count: int) -> int:
    """Validate and remove spies from the origin city for spy missions."""

    if spy_count <= 0:
        raise ValueError("Spy missions require at least one spy")
    spy_troop = (
        db.query(models.Troop)
        .filter(models.Troop.city_id == origin_city.id, models.Troop.unit_type == "spy")
        .first()
    )
    if not spy_troop or spy_troop.quantity < spy_count:
        raise ValueError("Not enough spies to send this mission")
    spy_troop.quantity -= spy_count
    db.add(spy_troop)
    db.commit()
    db.refresh(spy_troop)
    return spy_count


def _deduct_troops(db: Session, city: models.City, troops: Dict[str, int]):
    """Validate and remove troops from the origin city."""
    for unit, amount in troops.items():
        if amount <= 0:
            continue
        troop = (
            db.query(models.Troop)
            .filter(models.Troop.city_id == city.id, models.Troop.unit_type == unit)
            .first()
        )
        if not troop or troop.quantity < amount:
            raise ValueError(f"Not enough {unit}")
        troop.quantity -= amount


def send_movement(
    db: Session,
    origin_city: models.City,
    target_city_id: int | None,
    movement_type: str,
    troops: Dict[str, int] = None,
    resources: Dict[str, int] = None,
    spy_count: int = 0,
    target_city: models.City | None = None,
    target_building: str | None = None,
    target_oasis_id: int | None = None,
) -> models.Movement:
    """Create a movement entry, validate ownership and apply modifiers."""
    troops = troops or {}
    resources = resources or {}

    if target_city_id:
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
        
        target_x, target_y = target_city.x, target_city.y
    elif target_oasis_id:
        target_oasis = db.query(models.Oasis).filter(models.Oasis.id == target_oasis_id).first()
        if not target_oasis:
            raise ValueError("Target oasis not found")
        if target_oasis.world_id != origin_city.world_id:
            raise ValueError("Target oasis is not in the same world")
        
        target_x, target_y = target_oasis.x, target_oasis.y
    else:
        raise ValueError("No target specified")

    if movement_type == "spy":
        spy_count = _prepare_spy_mission(db, origin_city, spy_count)
    elif movement_type in ["attack", "reinforce"]:
        _deduct_troops(db, origin_city, troops)
    
    anticheat.check_action_speed(db, origin_city.owner, "movement")

    base_speed = _get_base_speed(movement_type)
    modifiers = event_service.get_active_modifiers(db)
    effective_speed = base_speed * modifiers.get("movement_speed", 1.0)
    speed_modifier = origin_city.world.speed_modifier if origin_city.world else 1.0
    speed = max(effective_speed * speed_modifier, 0.01)

    distance = math.hypot(origin_city.x - target_x, origin_city.y - target_y)
    hours = distance / speed
    arrival_time = utc_now() + timedelta(hours=hours)

    if target_city:
        anticheat.check_movement_legitimacy(
            db,
            origin_city,
            target_city,
            movement_type,
            arrival_time,
            speed,
            spy_count,
        )

    movement_obj = models.Movement(
        origin_city_id=origin_city.id,
        target_city_id=target_city_id,
        target_oasis_id=target_oasis_id,
        movement_type=movement_type,
        troops=troops,
        resources=resources,
        spy_count=spy_count,
        arrival_time=arrival_time,
        speed_used=speed,
        world_id=origin_city.world_id,
        target_building=target_building
    )
    db.add(movement_obj)
    db.commit()
    db.refresh(movement_obj)

    if movement_type == "attack" and target_city and target_city.owner:
        notification_service.create_notification(
            db,
            target_city.owner,
            title="¡Estás bajo ataque!",
            body=f"{origin_city.name} ha enviado tropas hacia tu ciudad {target_city.name}.",
            notification_type="attack_incoming",
        )
    if origin_city.owner:
        if movement_type == "attack":
            event_type = "attack_sent"
        elif movement_type == "spy":
            event_type = "spy_sent"
        else:
            event_type = None

        if event_type:
            quest_service.handle_event(db, origin_city.owner, event_type, {"movement_id": movement_obj.id})

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


def process_movements(db: Session) -> List[models.Movement]:
    """Mark movements that have reached their arrival time as arrived."""

    now = utc_now()
    arrived_movements = (
        db.query(models.Movement)
        .filter(models.Movement.status == "ongoing", models.Movement.arrival_time <= now)
        .all()
    )
    for movement in arrived_movements:
        movement.status = "arrived"
        db.add(movement)
    db.commit()
    return arrived_movements


def resolve_due_movements(db: Session) -> List[models.Movement]:
    """Resolve movements that have arrived."""

    now = utc_now()
    movements = (
        db.query(models.Movement)
        .options(
            selectinload(models.Movement.origin_city).selectinload(models.City.owner),
            selectinload(models.Movement.target_city).selectinload(models.City.owner),
            selectinload(models.Movement.target_city).selectinload(models.City.troops),
            selectinload(models.Movement.target_city).selectinload(models.City.buildings),
            selectinload(models.Movement.target_oasis)
        )
        .filter(models.Movement.arrival_time <= now, models.Movement.status == "ongoing")
        .all()
    )
    resolved = []
    for movement in movements:
        if movement.movement_type == "spy":
            _, _, surviving_spies = espionage.resolve_spy(db, movement)
            if surviving_spies > 0:
                # Create return movement for spies
                distance = calculate_distance(movement.target_city, movement.origin_city)
                speed = movement.speed_used or 1.0
                hours = distance / speed
                arrival_time = utc_now() + timedelta(hours=hours)
                
                return_move = models.Movement(
                    origin_city_id=movement.target_city_id,
                    target_city_id=movement.origin_city_id,
                    movement_type="return",
                    troops={"spy": surviving_spies},
                    arrival_time=arrival_time,
                    speed_used=speed,
                    world_id=movement.world_id
                )
                db.add(return_move)
        elif movement.movement_type == "attack":
            if movement.target_oasis_id:
                _resolve_oasis_attack(db, movement)
            else:
                _resolve_attack(db, movement)
        elif movement.movement_type == "reinforce":
            _resolve_reinforce(db, movement)
        elif movement.movement_type == "transport":
            _resolve_transport(db, movement)
        elif movement.movement_type == "transport_return":
            if movement.target_city.owner:
                notification_service.create_notification(
                    db,
                    movement.target_city.owner,
                    title="Comerciantes regresaron",
                    body=f"Tus comerciantes han regresado de {movement.origin_city.name}.",
                    notification_type="transport_return",
                )
        elif movement.movement_type == "return":
            _resolve_return(db, movement)
            
        movement.status = "completed"
        db.add(movement)
        resolved.append(movement)
    db.commit()
    return resolved


def _resolve_transport(db: Session, movement: models.Movement):
    """Deliver resources to target city."""
    target = movement.target_city
    resources = movement.resources or {}
    
    target.wood += resources.get("wood", 0)
    target.clay += resources.get("clay", 0)
    target.iron += resources.get("iron", 0)
    
    # Notification for target
    if target.owner:
        notification_service.create_notification(
            db,
            target.owner,
            title="Recursos recibidos",
            body=f"Has recibido recursos de {movement.origin_city.name}: "
                 f"Madera: {resources.get('wood', 0)}, "
                 f"Barro: {resources.get('clay', 0)}, "
                 f"Hierro: {resources.get('iron', 0)}",
            notification_type="transport_received",
        )

    # Create Trade Report
    report_service.create_trade_report(db, movement.origin_city, movement.target_city, resources)
        
    # Create return movement (merchants returning)
    distance = calculate_distance(movement.target_city, movement.origin_city)
    speed = movement.speed_used or 1.0
    hours = distance / speed
    arrival_time = utc_now() + timedelta(hours=hours)
    
    total_capacity = sum(resources.values())

    return_move = models.Movement(
        origin_city_id=movement.target_city_id,
        target_city_id=movement.origin_city_id,
        movement_type="transport_return",
        troops={},
        resources={"capacity": total_capacity},
        arrival_time=arrival_time,
        speed_used=speed,
        world_id=movement.world_id
    )
    db.add(return_move)


def _resolve_return(db: Session, movement: models.Movement):
    """Add returning troops back to origin city."""
    city = movement.target_city
    troops = movement.troops or {}
    for unit, amount in troops.items():
        troop = (
            db.query(models.Troop)
            .filter(models.Troop.city_id == city.id, models.Troop.unit_type == unit)
            .first()
        )
        if not troop:
            troop = models.Troop(city_id=city.id, unit_type=unit, quantity=0)
            db.add(troop)
        troop.quantity += amount

    # Create Return Report
    report_service.create_return_report(db, movement.target_city, movement.origin_city, troops)


def _resolve_reinforce(db: Session, movement: models.Movement):
    """Add reinforcement troops to target city."""
    city = movement.target_city
    troops = movement.troops or {}
    for unit, amount in troops.items():
        troop = (
            db.query(models.Troop)
            .filter(models.Troop.city_id == city.id, models.Troop.unit_type == unit)
            .first()
        )
        if not troop:
            troop = models.Troop(city_id=city.id, unit_type=unit, quantity=0)
            db.add(troop)
        troop.quantity += amount

    # Create Reinforce Report
    report_service.create_reinforce_report(db, movement.origin_city, movement.target_city, troops)



def _resolve_attack(db: Session, movement: models.Movement):
    """Resolve combat."""
    attacker = movement.origin_city
    defender = movement.target_city
    troops = movement.troops or {}
    
    report_data = combat.resolve_battle(
        attacker, 
        defender, 
        troops, 
        target_building=movement.target_building
    )
    
    # Apply defender losses
    defender_losses = report_data.get("defender_losses", {})
    for unit, loss in defender_losses.items():
        troop = next((t for t in defender.troops if t.unit_type == unit), None)
        if troop:
            troop.quantity = max(0, troop.quantity - loss)
            
    # Apply Hero XP
    xp_gained = report_data.get("xp_gained", 0)
    if xp_gained > 0 and attacker.owner and attacker.owner.hero:
        from . import hero as hero_service
        hero_service.add_xp(db, attacker.owner.hero, xp_gained)

    # Create report
    json_content = combat.build_battle_report_content(attacker, defender, report_data)
    report = models.Report(
        city_id=attacker.id,
        world_id=movement.world_id,
        report_type="battle",
        content=json_content,
        attacker_city_id=attacker.id,
        defender_city_id=defender.id
    )
    db.add(report)
    
    # Also create report for defender
    report_def = models.Report(
        city_id=defender.id,
        world_id=movement.world_id,
        report_type="battle",
        content=json_content,
        attacker_city_id=attacker.id,
        defender_city_id=defender.id
    )
    db.add(report_def)
    
    # Handle survivors (return trip)
    survivors = report_data.get("attacker_survivors", {})
    if sum(survivors.values()) > 0:
        distance = calculate_distance(defender, attacker)
        speed = movement.speed_used or 1.0
        hours = distance / speed
        arrival_time = utc_now() + timedelta(hours=hours)
        
        return_move = models.Movement(
            origin_city_id=defender.id,
            target_city_id=attacker.id,
            movement_type="return",
            troops=survivors,
            arrival_time=arrival_time,
            speed_used=speed,
            world_id=movement.world_id
        )
        db.add(return_move)


def _resolve_oasis_attack(db: Session, movement: models.Movement):
    """Resolve combat against an oasis."""
    attacker = movement.origin_city
    oasis = movement.target_oasis
    troops = movement.troops or {}
    
    attacker_hero = attacker.owner.hero if attacker.owner else None
    
    report_data = combat.resolve_oasis_battle(
        attacker,
        oasis,
        troops,
        attacker_hero=attacker_hero
    )
    
    # Apply losses to oasis
    defender_losses = report_data.get("defender_losses", {})
    oasis_troops = oasis.troops or {}
    for unit, loss in defender_losses.items():
        oasis_troops[unit] = max(0, oasis_troops.get(unit, 0) - loss)
    oasis.troops = oasis_troops # Update JSON
    
    # Check conquest
    if report_data.get("conquered"):
        oasis.owner_city_id = attacker.id
        oasis.troops = {} 
        
        if attacker.owner:
             notification_service.create_notification(
                db,
                attacker.owner,
                title="¡Oasis Conquistado!",
                body=f"Has conquistado un oasis en ({oasis.x}, {oasis.y}).",
                notification_type="conquest",
            )
            
    # Apply Hero XP
    xp_gained = report_data.get("xp_gained", 0)
    if xp_gained > 0 and attacker.owner and attacker.owner.hero:
        from . import hero as hero_service
        hero_service.add_xp(db, attacker.owner.hero, xp_gained)

    # Create report
    json_content = combat.build_oasis_report_content(attacker, oasis, report_data)
    report = models.Report(
        city_id=attacker.id,
        world_id=movement.world_id,
        report_type="battle",
        content=json_content,
        attacker_city_id=attacker.id,
        defender_city_id=None
    )
    db.add(report)
    
    # Handle survivors (return trip)
    survivors = report_data.get("attacker_survivors", {})
    if sum(survivors.values()) > 0:
        distance = math.hypot(attacker.x - oasis.x, attacker.y - oasis.y)
        speed = movement.speed_used or 1.0
        hours = distance / speed
        arrival_time = utc_now() + timedelta(hours=hours)
        
        return_move = models.Movement(
            origin_city_id=attacker.id, # Fake origin as attacker city
            target_city_id=attacker.id,
            movement_type="return",
            troops=survivors,
            arrival_time=arrival_time,
            speed_used=speed,
            world_id=movement.world_id
        )
        db.add(return_move)


def _city_troops_as_dict(city: models.City) -> Dict[str, int]:
    """Return troop quantities keyed by unit type for a city."""

    return {troop.unit_type: troop.quantity for troop in city.troops}


def _apply_losses_to_city(db: Session, city: models.City, losses: Dict[str, int]):
    """Apply combat losses to troops within a city."""

    for troop in city.troops:
        loss = losses.get(troop.unit_type, 0)
        if loss:
            troop.quantity = max(0, troop.quantity - loss)
            db.add(troop)


def process_arrived_movements(db: Session) -> List[models.Movement]:
    """Resolve combats for movements that have arrived and notify players."""

    now = utc_now()
    modifiers = event_service.get_active_modifiers(db)
    arriving_movements = (
        db.query(models.Movement)
        .filter(models.Movement.arrival_time <= now, models.Movement.status == "ongoing")
        .all()
    )
    for movement in arriving_movements:
        if movement.movement_type == "attack":
            attacker_city = (
                db.query(models.City)
                .options(selectinload(models.City.troops), selectinload(models.City.owner), selectinload(models.City.buildings))
                .filter(models.City.id == movement.origin_city_id)
                .first()
            )
            defender_city = (
                db.query(models.City)
                .options(selectinload(models.City.troops), selectinload(models.City.owner), selectinload(models.City.buildings))
                .filter(models.City.id == movement.target_city_id)
                .first()
            )
            if not attacker_city or not defender_city:
                movement.status = "completed"
                db.add(movement)
                continue

            attacking_troops = _city_troops_as_dict(attacker_city)
            anticheat.check_movement_legitimacy(
                db,
                attacker_city,
                defender_city,
                movement.movement_type,
                movement.arrival_time,
                movement.speed_used or UNIT_SPEED.get("basic_infantry", 0.6),
            )
            battle_result = combat.resolve_battle(
                attacker_city,
                defender_city,
                attacking_troops,
                modifiers,
            )
            _apply_losses_to_city(db, attacker_city, battle_result["attacker_losses"])
            _apply_losses_to_city(db, defender_city, battle_result["defender_losses"])

            report_html = combat.build_battle_report_html(
                attacker_city,
                defender_city,
                battle_result,
            )

            attacker_report = models.Report(
                city_id=attacker_city.id,
                report_type="battle",
                content=report_html,
                attacker_city_id=attacker_city.id,
                defender_city_id=defender_city.id,
                world_id=attacker_city.world_id,
            )
            defender_report = models.Report(
                city_id=defender_city.id,
                report_type="battle",
                content=report_html,
                attacker_city_id=attacker_city.id,
                defender_city_id=defender_city.id,
                world_id=defender_city.world_id,
            )
            db.add(attacker_report)
            db.add(defender_report)

            defender_survivors = battle_result.get("defender_survivors", {})
            if sum(defender_survivors.values()) == 0:
                from .achievement import update_achievement_progress

                update_achievement_progress(
                    db,
                    attacker_city.owner_id,
                    "win_battles",
                    increment=1,
                )
            if attacker_city.owner:
                notification_service.create_notification(
                    db,
                    attacker_city.owner,
                    title="Informe de batalla listo",
                    body=f"Tu ataque contra {defender_city.name} ha generado un informe.",
                    notification_type="report_ready",
                    allow_email=False,
                )
            if defender_city.owner:
                notification_service.create_notification(
                    db,
                    defender_city.owner,
                    title="Has recibido un informe de batalla",
                    body=f"Tu ciudad {defender_city.name} ha sido atacada. Hay un nuevo informe disponible.",
                    notification_type="report_ready",
                    allow_email=False,
                )
            logger.info(
                "combat_resolved",
                extra={
                    "movement_id": movement.id,
                    "attacker_city_id": attacker_city.id,
                    "defender_city_id": defender_city.id,
                    "attacker_losses": battle_result.get("attacker_losses", {}),
                    "defender_losses": battle_result.get("defender_losses", {}),
                },
            )

        movement.status = "completed"
        db.add(movement)
    db.commit()
    return arriving_movements

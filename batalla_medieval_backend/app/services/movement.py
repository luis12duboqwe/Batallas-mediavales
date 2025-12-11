import math
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .. import models
from . import espionage
from . import combat
from . import quest as quest_service
from . import combat, espionage

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
    return math.hypot(origin.x - target.x, origin.y - target.y)


def send_movement(
    db: Session,
    origin_city: models.City,
    target_city_id: int,
    movement_type: str,
    target_city: models.City | None = None,
    spy_count: int = 0,
) -> models.Movement:
    target_city = target_city or db.query(models.City).filter(models.City.id == target_city_id).first()
    if not target_city:
        raise ValueError("Target city not found")
    if target_city.world_id != origin_city.world_id:
        raise ValueError("Target city is not in the same world")

    if movement_type != "spy":
        spy_count = 0
    if movement_type == "spy":
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

    base_speed = UNIT_SPEED.get("fast_cavalry" if movement_type == "spy" else "basic_infantry", 0.6)
    speed_modifier = origin_city.world.speed_modifier if origin_city.world else 1.0
    speed = base_speed * speed_modifier
    distance = calculate_distance(origin_city, target_city)
    hours = distance / speed if speed else 0
    arrival_time = datetime.utcnow() + timedelta(hours=hours)
    movement = models.Movement(
        origin_city_id=origin_city.id,
        target_city_id=target_city.id,
        movement_type=movement_type,
        spy_count=spy_count,
        arrival_time=arrival_time,
        world_id=origin_city.world_id,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)

    if origin_city.owner:
        event_type = None
        if movement_type == "attack":
            event_type = "attack_sent"
        elif movement_type == "spy":
            event_type = "spy_sent"
        if event_type:
            quest_service.handle_event(db, origin_city.owner, event_type, {"movement_id": movement.id})

    return movement


def process_movements(db: Session) -> list[models.Movement]:
    now = datetime.utcnow()
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


def resolve_due_movements(db: Session):
    now = datetime.utcnow()
    movements = (
        db.query(models.Movement)
        .filter(models.Movement.arrival_time <= now, models.Movement.status == "ongoing")
        .all()
    )
    resolved = []
    for movement in movements:
        if movement.movement_type == "spy":
            espionage.resolve_spy(db, movement)
        movement.status = "completed"
        db.add(movement)
        resolved.append(movement)
    db.commit()
    return resolved


def _city_troops_as_dict(city: models.City) -> dict[str, int]:
    return {troop.unit_type: troop.quantity for troop in city.troops}


def _apply_losses_to_city(db: Session, city: models.City, losses: dict[str, int]):
    for troop in city.troops:
        loss = losses.get(troop.unit_type, 0)
        if loss:
            troop.quantity = max(0, troop.quantity - loss)
            db.add(troop)


def process_arrived_movements(db: Session):
    now = datetime.utcnow()
    arriving_movements = (
        db.query(models.Movement)
        .filter(models.Movement.arrival_time <= now, models.Movement.status == "ongoing")
        .all()
    )
    for movement in arriving_movements:
        if movement.movement_type == "attack":
            attacker_city = db.query(models.City).filter(models.City.id == movement.origin_city_id).first()
            defender_city = db.query(models.City).filter(models.City.id == movement.target_city_id).first()
            if not attacker_city or not defender_city:
                movement.status = "completed"
                db.add(movement)
                continue

            attacking_troops = _city_troops_as_dict(attacker_city)
            battle_result = combat.resolve_battle(attacker_city, defender_city, attacking_troops)

            _apply_losses_to_city(db, attacker_city, battle_result["attacker_losses"])
            _apply_losses_to_city(db, defender_city, battle_result["defender_losses"])

            report_html = combat.build_battle_report_html(attacker_city, defender_city, battle_result)

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

        movement.status = "completed"
        db.add(movement)
    db.commit()

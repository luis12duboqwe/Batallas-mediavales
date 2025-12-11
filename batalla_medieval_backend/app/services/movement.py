from datetime import datetime, timedelta
import math

from sqlalchemy.orm import Session

from .. import models
from . import combat

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


def _sanitize_troops_payload(troops_payload: dict[str, int]) -> dict[str, int]:
    return {unit: max(0, qty) for unit, qty in troops_payload.items() if qty > 0}


def _deduct_troops_from_city(db: Session, city: models.City, troops_payload: dict[str, int]):
    available = {troop.unit_type: troop for troop in city.troops}
    for unit_type, quantity in troops_payload.items():
        troop = available.get(unit_type)
        if troop is None or troop.quantity < quantity:
            raise ValueError(f"Not enough {unit_type} to send")
        troop.quantity -= quantity
        db.add(troop)


def send_movement(
    db: Session,
    origin_city: models.City,
    target_city_id: int,
    movement_type: str,
    troops_payload: dict[str, int],
) -> models.Movement:
    target_city = db.query(models.City).filter(models.City.id == target_city_id).first()
    if not target_city:
        raise ValueError("Target city not found")

    sanitized_troops = _sanitize_troops_payload(troops_payload)
    if not sanitized_troops:
        raise ValueError("No troops provided for movement")

    _deduct_troops_from_city(db, origin_city, sanitized_troops)
    speed = UNIT_SPEED.get("fast_cavalry" if movement_type == "spy" else "basic_infantry", 0.6)
    distance = calculate_distance(origin_city, target_city)
    hours = distance / speed
    arrival_time = datetime.utcnow() + timedelta(hours=hours)
    movement = models.Movement(
        origin_city_id=origin_city.id,
        target_city_id=target_city.id,
        movement_type=movement_type,
        arrival_time=arrival_time,
        troops_payload=sanitized_troops,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


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
    arriving_movements = db.query(models.Movement).filter(models.Movement.arrival_time <= now, models.Movement.status == "ongoing").all()
    for movement in arriving_movements:
        if movement.movement_type == "attack":
            attacker_city = db.query(models.City).filter(models.City.id == movement.origin_city_id).first()
            defender_city = db.query(models.City).filter(models.City.id == movement.target_city_id).first()
            if not attacker_city or not defender_city:
                movement.status = "completed"
                db.add(movement)
                continue

            attacking_troops = movement.troops_payload or {}
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
            )
            defender_report = models.Report(
                city_id=defender_city.id,
                report_type="battle",
                content=report_html,
                attacker_city_id=attacker_city.id,
                defender_city_id=defender_city.id,
            )
            db.add(attacker_report)
            db.add(defender_report)

        movement.status = "completed"
        db.add(movement)
    db.commit()

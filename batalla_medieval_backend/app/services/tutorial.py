"""Server-authoritative tutorial progression for the G2 vertical slice."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .. import models
from . import production

FINAL_STEP = 7
TUTORIAL_REWARD = {"wood": 250, "clay": 250, "iron": 250}

STEP_LABELS = {
    0: "Únete a un mundo para recibir tu capital.",
    1: "Construye un cuartel de nivel 1.",
    2: "Entrena al menos una unidad de infantería básica.",
    3: "Abre el mapa y localiza una aldea bárbara.",
    4: "Envía un ataque contra una aldea bárbara.",
    5: "Espera a que el worker resuelva el ataque y genere el informe.",
    6: "Espera el retorno de tus tropas a la capital.",
    7: "Tutorial completado.",
}


def _active_city(db: Session, user: models.User) -> models.City | None:
    query = db.query(models.City).filter(models.City.owner_id == user.id)
    if user.world_id is not None:
        query = query.filter(models.City.world_id == user.world_id)
    return query.order_by(models.City.id.asc()).first()


def _has_barbarian(db: Session, world_id: int) -> bool:
    return (
        db.query(models.City.id)
        .filter(models.City.world_id == world_id, models.City.owner_id.is_(None))
        .first()
        is not None
    )


def _derive_step(db: Session, user: models.User, city: models.City | None) -> int:
    if city is None:
        return 0

    step = 1
    barracks = (
        db.query(models.Building.id)
        .filter(
            models.Building.city_id == city.id,
            models.Building.name == "barracks",
            models.Building.level >= 1,
        )
        .first()
    )
    if not barracks:
        return step
    step = 2

    trained = (
        db.query(models.Troop.id)
        .filter(
            models.Troop.city_id == city.id,
            models.Troop.unit_type == "basic_infantry",
            models.Troop.quantity > 0,
        )
        .first()
    )
    if not trained:
        # An already-dispatched attack is durable proof that usable troops had
        # been trained even if all of them are currently marching.
        trained = (
            db.query(models.Movement.id)
            .filter(
                models.Movement.origin_city_id == city.id,
                models.Movement.movement_type == "attack",
            )
            .first()
        )
    if not trained:
        return step
    step = 3

    if not _has_barbarian(db, city.world_id):
        return step
    step = 4

    attack = (
        db.query(models.Movement.id)
        .filter(
            models.Movement.origin_city_id == city.id,
            models.Movement.world_id == city.world_id,
            models.Movement.movement_type == "attack",
        )
        .first()
    )
    if not attack:
        return step
    step = 5

    battle_report = (
        db.query(models.Report.id)
        .filter(
            models.Report.city_id == city.id,
            models.Report.world_id == city.world_id,
            models.Report.report_type == "battle",
        )
        .first()
    )
    if not battle_report:
        return step
    step = 6

    return_report = (
        db.query(models.Report.id)
        .filter(
            models.Report.city_id == city.id,
            models.Report.world_id == city.world_id,
            models.Report.report_type == "return",
        )
        .first()
    )
    if return_report:
        step = FINAL_STEP
    return step


def _grant_reward(db: Session, city: models.City) -> dict[str, float]:
    locked_city = (
        db.query(models.City)
        .filter(models.City.id == city.id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    storage_limit = production.get_storage_limit(locked_city)
    granted: dict[str, float] = {}
    for resource, requested in TUTORIAL_REWARD.items():
        current = float(getattr(locked_city, resource))
        new_value = current if current >= storage_limit else min(current + requested, storage_limit)
        granted[resource] = max(new_value - current, 0.0)
        setattr(locked_city, resource, new_value)
    db.add(locked_city)
    return granted


def sync_progress(db: Session, user: models.User) -> dict[str, Any]:
    """Recompute tutorial progress from durable state and grant reward once."""

    locked_user = (
        db.query(models.User)
        .filter(models.User.id == user.id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    city = _active_city(db, locked_user)
    derived_step = _derive_step(db, locked_user, city)
    locked_user.tutorial_step = max(min(derived_step, FINAL_STEP), locked_user.tutorial_step)

    granted: dict[str, float] = {}
    if derived_step >= FINAL_STEP and not locked_user.tutorial_reward_claimed:
        if city is None:
            raise RuntimeError("Tutorial completed without an owned city")
        granted = _grant_reward(db, city)
        locked_user.tutorial_reward_claimed = True
        locked_user.tutorial_step = FINAL_STEP

    db.add(locked_user)
    db.commit()
    db.refresh(locked_user)

    step = min(int(locked_user.tutorial_step or 0), FINAL_STEP)
    return {
        "step": step,
        "total_steps": FINAL_STEP,
        "completed": step >= FINAL_STEP,
        "reward_claimed": bool(locked_user.tutorial_reward_claimed),
        "reward": TUTORIAL_REWARD if locked_user.tutorial_reward_claimed else None,
        "reward_granted_now": granted,
        "next_action": STEP_LABELS[step],
    }

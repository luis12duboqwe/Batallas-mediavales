"""Server-authoritative tutorial progression for the G2/G4 first session."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .. import models
from . import balance, production

FINAL_STEP = 7
TUTORIAL_REWARD = balance.TUTORIAL_REWARD

STEP_LABELS = {
    0: "Únete a un mundo para recibir tu capital.",
    1: "Construye un cuartel de nivel 1.",
    2: "Entrena al menos una unidad de infantería básica.",
    3: "Abre el mapa y localiza una aldea bárbara.",
    4: "Envía un ataque contra una aldea bárbara.",
    5: "Espera a que el worker resuelva el ataque y genere el informe.",
    6: "Espera el retorno de tus tropas; si fueron derrotadas por completo, el tutorial se cerrará automáticamente.",
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


def _battle_requires_return(report: models.Report) -> bool:
    """Return whether the persisted battle result should create a return march.

    ``movement._resolve_attack_core`` creates a return when at least one
    attacker survives or when there is loot to carry home. If the attacker is
    wiped out and earns no loot, no return movement exists by design. Tutorial
    progress must therefore treat that resolved defeat as terminal instead of
    waiting forever for a report that can never be generated.

    Malformed/legacy reports fail closed (``True``) so a bad payload never
    grants tutorial completion by accident.
    """

    try:
        payload = json.loads(report.content or "{}")
        attacker = payload.get("attacker") or {}
        initial = attacker.get("initial") or {}
        losses = attacker.get("losses") or {}
        survivors = any(
            max(int(amount or 0) - int(losses.get(unit, 0) or 0), 0) > 0
            for unit, amount in initial.items()
        )
        loot = payload.get("loot") or {}
        has_loot = any(float(loot.get(resource, 0) or 0) > 0 for resource in balance.RESOURCE_FIELDS)
        return survivors or has_loot
    except (TypeError, ValueError, json.JSONDecodeError):
        return True


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
        db.query(models.Report)
        .filter(
            models.Report.city_id == city.id,
            models.Report.world_id == city.world_id,
            models.Report.report_type == "battle",
            models.Report.attacker_city_id == city.id,
        )
        .order_by(models.Report.id.desc())
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
    if return_report or not _battle_requires_return(battle_report):
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


def _response(
    *,
    user: models.User,
    step: int,
    granted: dict[str, float] | None = None,
) -> dict[str, Any]:
    step = max(0, min(int(step), FINAL_STEP))
    reward_claimed = bool(user.tutorial_reward_claimed)
    return {
        "step": step,
        "total_steps": FINAL_STEP,
        "completed": step >= FINAL_STEP,
        "reward_claimed": reward_claimed,
        "reward": TUTORIAL_REWARD if reward_claimed else None,
        "reward_granted_now": granted or {},
        "next_action": STEP_LABELS[step],
    }


def get_progress(db: Session, user: models.User) -> dict[str, Any]:
    """Return current tutorial state without acquiring write locks or committing."""

    fresh_user = db.query(models.User).filter(models.User.id == user.id).one()
    city = _active_city(db, fresh_user)
    derived_step = _derive_step(db, fresh_user, city)
    persisted_step = int(fresh_user.tutorial_step or 0)
    step = max(derived_step, persisted_step)
    if fresh_user.tutorial_reward_claimed:
        step = FINAL_STEP
    return _response(user=fresh_user, step=step)


def sync_progress(db: Session, user: models.User) -> dict[str, Any]:
    """Persist verified progress and claim the final reward exactly once."""

    locked_user = (
        db.query(models.User)
        .filter(models.User.id == user.id)
        .with_for_update()
        .populate_existing()
        .one()
    )
    city = _active_city(db, locked_user)
    derived_step = _derive_step(db, locked_user, city)
    new_step = max(min(derived_step, FINAL_STEP), int(locked_user.tutorial_step or 0))
    changed = new_step != int(locked_user.tutorial_step or 0)
    locked_user.tutorial_step = new_step

    granted: dict[str, float] = {}
    if derived_step >= FINAL_STEP and not locked_user.tutorial_reward_claimed:
        if city is None:
            raise RuntimeError("Tutorial completed without an owned city")
        granted = _grant_reward(db, city)
        locked_user.tutorial_reward_claimed = True
        locked_user.tutorial_step = FINAL_STEP
        changed = True

    if changed:
        db.add(locked_user)
        db.commit()
        db.refresh(locked_user)
    else:
        db.rollback()
        locked_user = db.query(models.User).filter(models.User.id == user.id).one()

    step = max(int(locked_user.tutorial_step or 0), derived_step)
    if locked_user.tutorial_reward_claimed:
        step = FINAL_STEP
    return _response(user=locked_user, step=step, granted=granted)

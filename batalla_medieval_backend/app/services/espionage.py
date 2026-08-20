from __future__ import annotations

import json
import random
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from .. import models
from . import balance
from . import event as event_service


def calculate_success(attacker_spies: int, defender_spies: int) -> float:
    return attacker_spies / (defender_spies + balance.SPY_DEFENDER_OFFSET)


def build_report_content(
    *,
    attacker_city: models.City,
    defender_city: models.City,
    success: bool,
    success_chance: float,
    reported_as_unknown: bool,
    attacker_spies: int,
    defender_spies: int,
    resources: Dict[str, float] | None = None,
    troops: Dict[str, int] | None = None,
    buildings: Dict[str, int] | None = None,
) -> str:
    attacker_name = "Desconocido" if reported_as_unknown else attacker_city.name
    return json.dumps(
        {
            "type": "spy",
            "attacker": {"name": attacker_name, "spies": attacker_spies},
            "defender": {"name": defender_city.name, "spies": defender_spies},
            "success": success,
            "success_chance": success_chance,
            "resources": resources,
            "troops": troops,
            "buildings": buildings,
        }
    )


def resolve_spy(
    db: Session, movement: models.Movement
) -> Tuple[models.Report, models.Report, int]:
    """Resolve espionage without committing the caller's transaction."""

    attacker_city = movement.origin_city or (
        db.query(models.City).filter(models.City.id == movement.origin_city_id).first()
    )
    defender_city = movement.target_city or (
        db.query(models.City).filter(models.City.id == movement.target_city_id).first()
    )
    if not attacker_city or not defender_city:
        raise ValueError("Spy movement references a missing city")

    attacker_spies = int(movement.spy_count or 0)
    defender_spy_troop = (
        db.query(models.Troop)
        .filter(
            models.Troop.city_id == defender_city.id,
            models.Troop.unit_type == "spy",
        )
        .first()
    )
    defender_spies = defender_spy_troop.quantity if defender_spy_troop else 0

    modifiers = event_service.get_active_modifiers(db, world_id=movement.world_id)
    success_chance = calculate_success(attacker_spies, defender_spies)
    success_chance *= modifiers.get("spy_modifier", 1.0)
    success_chance = min(1.0, max(0.0, success_chance))
    success = random.random() < success_chance
    surviving_spies = attacker_spies if success else 0

    reported_as_unknown = bool(
        not success and random.random() < balance.SPY_UNKNOWN_ATTACKER_CHANCE
    )
    resources = {
        resource: float(getattr(defender_city, resource))
        for resource in balance.RESOURCE_FIELDS
    }
    troops = {troop.unit_type: troop.quantity for troop in defender_city.troops}
    buildings = {building.name: building.level for building in defender_city.buildings}

    attacker_report = models.Report(
        city_id=attacker_city.id,
        world_id=movement.world_id,
        report_type="spy",
        content=build_report_content(
            attacker_city=attacker_city,
            defender_city=defender_city,
            success=success,
            success_chance=success_chance,
            reported_as_unknown=False,
            attacker_spies=attacker_spies,
            defender_spies=defender_spies,
            resources=resources if success else None,
            troops=troops if success else None,
            buildings=(
                buildings
                if success and balance.SPY_REVEALS_BUILDINGS_ON_SUCCESS
                else None
            ),
        ),
        attacker_city_id=attacker_city.id,
        defender_city_id=defender_city.id,
    )
    defender_report = models.Report(
        city_id=defender_city.id,
        world_id=movement.world_id,
        report_type="spy",
        content=build_report_content(
            attacker_city=attacker_city,
            defender_city=defender_city,
            success=success,
            success_chance=success_chance,
            reported_as_unknown=reported_as_unknown,
            attacker_spies=attacker_spies,
            defender_spies=defender_spies,
        ),
        attacker_city_id=attacker_city.id,
        defender_city_id=defender_city.id,
    )
    db.add_all([attacker_report, defender_report])
    return attacker_report, defender_report, surviving_spies
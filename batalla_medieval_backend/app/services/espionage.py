from __future__ import annotations

import random
import json
from datetime import datetime
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from .. import models
from ..utils import utc_now
from . import notification as notification_service
from . import anticheat
from . import event as event_service


def calculate_success(attacker_spies: int, defender_spies: int) -> float:
    return attacker_spies / (defender_spies + 1)


def build_report_content(
    *,
    attacker_city: models.City,
    defender_city: models.City,
    success: bool,
    reported_as_unknown: bool,
    attacker_spies: int,
    defender_spies: int,
    resources: Dict[str, float] | None = None,
    troops: Dict[str, int] | None = None,
    buildings: Dict[str, int] | None = None,
) -> str:
    attacker_name = "Desconocido" if reported_as_unknown else attacker_city.name
    
    report_data = {
        "type": "spy",
        "attacker": {
            "name": attacker_name,
            "spies": attacker_spies
        },
        "defender": {
            "name": defender_city.name,
            "spies": defender_spies
        },
        "success": success,
        "resources": resources,
        "troops": troops,
        "buildings": buildings
    }
    
    return json.dumps(report_data)


def resolve_spy(db: Session, movement: models.Movement) -> Tuple[models.SpyReport, models.SpyReport, int]:
    attacker_city = db.query(models.City).filter(models.City.id == movement.origin_city_id).first()
    defender_city = db.query(models.City).filter(models.City.id == movement.target_city_id).first()
    attacker_spies = movement.spy_count
    defender_spy_troop = (
        db.query(models.Troop)
        .filter(models.Troop.city_id == defender_city.id, models.Troop.unit_type == "spy")
        .first()
    )
    defender_spies = defender_spy_troop.quantity if defender_spy_troop else 0

    modifiers = event_service.get_active_modifiers(db)
    success_chance = calculate_success(attacker_spies, defender_spies)
    success_chance *= modifiers.get("spy_modifier", 1.0)
    success_chance = min(1.0, success_chance)
    success = random.random() < success_chance
    
    surviving_spies = attacker_spies if success else 0
    
    reported_as_unknown = False
    if not success and random.random() < 0.1:
        reported_as_unknown = True
    anticheat.check_spy_result(db, attacker_city.owner, success_chance, success)

    resources = {
        "wood": defender_city.wood,
        "clay": defender_city.clay,
        "iron": defender_city.iron,
    }
    troops = {troop.unit_type: troop.quantity for troop in defender_city.troops}
    buildings = {building.name: building.level for building in defender_city.buildings}

    attacker_content = build_report_content(
        attacker_city=attacker_city,
        defender_city=defender_city,
        success=success,
        reported_as_unknown=False,
        attacker_spies=attacker_spies,
        defender_spies=defender_spies,
        resources=resources if success else None,
        troops=troops if success else None,
        buildings=buildings if success else None,
    )
    
    defender_content = build_report_content(
        attacker_city=attacker_city,
        defender_city=defender_city,
        success=success,
        reported_as_unknown=reported_as_unknown,
        attacker_spies=attacker_spies,
        defender_spies=defender_spies,
        resources=None,
        troops=None,
        buildings=None,
    )

    attacker_report = models.Report(
        city_id=attacker_city.id,
        world_id=movement.world_id,
        report_type="spy",
        content=attacker_content,
        attacker_city_id=attacker_city.id,
        defender_city_id=defender_city.id
    )
    db.add(attacker_report)

    defender_report = models.Report(
        city_id=defender_city.id,
        world_id=movement.world_id,
        report_type="spy",
        content=defender_content,
        attacker_city_id=attacker_city.id,
        defender_city_id=defender_city.id
    )
    db.add(defender_report)

    return attacker_report, defender_report, surviving_spies

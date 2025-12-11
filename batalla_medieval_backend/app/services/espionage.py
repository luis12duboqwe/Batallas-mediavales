from __future__ import annotations

import random
from datetime import datetime
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from .. import models
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
    html = ["<h2>Informe de Espionaje</h2>"]
    html.append(f"<p><strong>Atacante:</strong> {attacker_name}</p>")
    html.append(f"<p><strong>Defensor:</strong> {defender_city.name}</p>")
    html.append(f"<p><strong>Resultado:</strong> {'Éxito' if success else 'Fallo'}</p>")
    html.append(
        f"<p><strong>Espías Atacantes:</strong> {attacker_spies} | "
        f"<strong>Espías Defensores:</strong> {defender_spies}</p>"
    )
    if success:
        if resources:
            html.append("<h3>Recursos</h3><ul>")
            for resource, amount in resources.items():
                html.append(f"<li>{resource.title()}: {amount:.0f}</li>")
            html.append("</ul>")
        if troops:
            html.append("<h3>Tropas</h3><ul>")
            for troop, qty in troops.items():
                html.append(f"<li>{troop}: {qty}</li>")
            html.append("</ul>")
        if buildings:
            html.append("<h3>Edificios</h3><ul>")
            for building, lvl in buildings.items():
                html.append(f"<li>{building}: Nivel {lvl}</li>")
            html.append("</ul>")
    else:
        html.append("<p>La misión ha fracasado y los espías han sido capturados.</p>")
    return "\n".join(html)


def resolve_spy(db: Session, movement: models.Movement) -> Tuple[models.SpyReport, models.SpyReport]:
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
        buildings=buildings if success and attacker_spies >= 5 else None,
    )

    defender_content = build_report_content(
        attacker_city=attacker_city,
        defender_city=defender_city,
        success=success,
        reported_as_unknown=reported_as_unknown,
        attacker_spies=attacker_spies,
        defender_spies=defender_spies,
        resources=resources if success else None,
        troops=troops if success else None,
        buildings=buildings if success and attacker_spies >= 5 else None,
    )

    attacker_report = models.SpyReport(
        city_id=attacker_city.id,
        attacker_city_id=attacker_city.id,
        defender_city_id=defender_city.id,
        success=success,
        reported_as_unknown=False,
        content=attacker_content,
        created_at=datetime.utcnow(),
    )
    defender_report = models.SpyReport(
        city_id=defender_city.id,
        attacker_city_id=None if reported_as_unknown else attacker_city.id,
        defender_city_id=defender_city.id,
        success=success,
        reported_as_unknown=reported_as_unknown,
        content=defender_content,
        created_at=datetime.utcnow(),
    )
    db.add(attacker_report)
    db.add(defender_report)
    db.commit()
    db.refresh(attacker_report)
    db.refresh(defender_report)
    return attacker_report, defender_report

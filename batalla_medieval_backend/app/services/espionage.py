from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, Tuple

from sqlalchemy.orm import Session

from .. import models
from . import balance
from . import event as event_service


ESPIONAGE_ALGORITHM_VERSION = "2026.08.24-bm0065-v1"

# BM-0065 owns the espionage algorithm. These values are deliberately scoped to
# espionage so changing them does not change BM-0064 combat seeds/results. They
# are surfaced in reports/wiki and will be mirrored by the public balance
# contract before the milestone is closed.
SPY_LUCK_MIN = -0.20
SPY_LUCK_MAX = 0.20
SPY_SUCCESS_CHANCE_MIN = 0.05
SPY_SUCCESS_CHANCE_MAX = 0.95
SPY_DETECTION_CHANCE_MIN = 0.05
SPY_DETECTION_CHANCE_MAX = 0.95
SPY_FAILURE_DETECTION_BONUS = 0.35
SPY_TROOP_INTEL_THRESHOLD = 1.0
SPY_BUILDING_INTEL_THRESHOLD = 2.0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def calculate_success(attacker_spies: int, defender_spies: int) -> float:
    """Compatibility helper returning the raw attacker/defender spy ratio."""

    attackers = max(int(attacker_spies), 0)
    defenders = max(int(defender_spies), 0)
    return attackers / (defenders + balance.SPY_DEFENDER_OFFSET)


def calculate_success_chance(
    attacker_spies: int,
    defender_spies: int,
    *,
    spy_modifier: float = 1.0,
    luck: float = 0.0,
) -> float:
    """Return the bounded authoritative chance that the mission gathers intel."""

    raw_ratio = calculate_success(attacker_spies, defender_spies)
    modified = raw_ratio * max(float(spy_modifier), 0.0) * (1.0 + float(luck))
    return _clamp(modified, SPY_SUCCESS_CHANCE_MIN, SPY_SUCCESS_CHANCE_MAX)


def calculate_detection_chance(
    attacker_spies: int,
    defender_spies: int,
    *,
    success: bool,
    luck: float = 0.0,
) -> float:
    """Return bounded defender detection chance, independent from mission success."""

    attackers = max(int(attacker_spies), 0)
    defenders = max(int(defender_spies), 0)
    base = defenders / (attackers + balance.SPY_DEFENDER_OFFSET)
    # Positive attacker luck helps both infiltration and stealth. A failed
    # mission is materially easier to notice, but detection still remains a
    # separate deterministic roll rather than being synonymous with failure.
    chance = base * (1.0 - float(luck))
    if not success:
        chance += SPY_FAILURE_DETECTION_BONUS
    return _clamp(chance, SPY_DETECTION_CHANCE_MIN, SPY_DETECTION_CHANCE_MAX)


def calculate_intel_level(
    attacker_spies: int,
    defender_spies: int,
    *,
    spy_modifier: float = 1.0,
    luck: float = 0.0,
    success: bool,
) -> int:
    """Return 0..3 where 1=resources, 2=+troops, 3=+buildings."""

    if not success:
        return 0
    score = (
        calculate_success(attacker_spies, defender_spies)
        * max(float(spy_modifier), 0.0)
        * (1.0 + float(luck))
    )
    if score >= SPY_BUILDING_INTEL_THRESHOLD:
        return 3
    if score >= SPY_TROOP_INTEL_THRESHOLD:
        return 2
    return 1


def _target_snapshot(defender_city: models.City) -> dict[str, Any]:
    return {
        "resources": {
            resource: round(float(getattr(defender_city, resource)), 6)
            for resource in balance.RESOURCE_FIELDS
        },
        "troops": sorted(
            (
                str(troop.unit_type),
                int(troop.quantity),
            )
            for troop in defender_city.troops
            if int(troop.quantity) > 0
        ),
        "buildings": sorted(
            (str(building.name), int(building.level))
            for building in defender_city.buildings
            if int(building.level) > 0
        ),
    }


def derive_seed(
    movement: models.Movement,
    *,
    attacker_spies: int,
    defender_spies: int,
    spy_modifier: float,
    defender_city: models.City,
) -> str:
    """Derive an auditable SHA-256 seed from the committed mission/pre-state."""

    payload = {
        "algorithm_version": ESPIONAGE_ALGORITHM_VERSION,
        "balance_version": balance.BALANCE_VERSION,
        "movement_id": int(movement.id or 0),
        "world_id": int(movement.world_id),
        "origin_city_id": int(movement.origin_city_id),
        "target_city_id": int(movement.target_city_id or 0),
        "attacker_spies": int(attacker_spies),
        "defender_spies": int(defender_spies),
        "spy_modifier": round(float(spy_modifier), 8),
        "target": _target_snapshot(defender_city),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_outcome(
    *,
    attacker_spies: int,
    defender_spies: int,
    spy_modifier: float,
    seed: str,
) -> dict[str, Any]:
    """Resolve the stochastic part from a local RNG so retries reproduce it."""

    rng = random.Random(seed)
    luck = rng.uniform(SPY_LUCK_MIN, SPY_LUCK_MAX)
    success_chance = calculate_success_chance(
        attacker_spies,
        defender_spies,
        spy_modifier=spy_modifier,
        luck=luck,
    )
    success_roll = rng.random()
    success = success_roll < success_chance
    detection_chance = calculate_detection_chance(
        attacker_spies,
        defender_spies,
        success=success,
        luck=luck,
    )
    detection_roll = rng.random()
    detected = detection_roll < detection_chance
    identified = bool(
        detected and rng.random() >= balance.SPY_UNKNOWN_ATTACKER_CHANCE
    )
    intel_level = calculate_intel_level(
        attacker_spies,
        defender_spies,
        spy_modifier=spy_modifier,
        luck=luck,
        success=success,
    )
    return {
        "algorithm_version": ESPIONAGE_ALGORITHM_VERSION,
        "balance_version": balance.BALANCE_VERSION,
        "seed": seed,
        "luck": luck,
        "success_chance": success_chance,
        "success_roll": success_roll,
        "success": success,
        "detection_chance": detection_chance,
        "detection_roll": detection_roll,
        "detected": detected,
        "attacker_identified": identified,
        "intel_level": intel_level,
    }


def build_report_content(
    *,
    attacker_city: models.City,
    defender_city: models.City,
    outcome: dict[str, Any],
    report_role: str,
    attacker_spies: int,
    defender_spies: int,
    resources: Dict[str, float] | None = None,
    troops: Dict[str, int] | None = None,
    buildings: Dict[str, int] | None = None,
) -> str:
    """Build a privacy-aware report for attacker or detected defender."""

    if report_role not in {"attacker", "defender"}:
        raise ValueError("report_role must be attacker or defender")

    identified = bool(outcome.get("attacker_identified", False))
    attacker_name = (
        attacker_city.name
        if report_role == "attacker" or identified
        else "Desconocido"
    )
    payload: dict[str, Any] = {
        "type": "spy",
        "role": report_role,
        "algorithm_version": outcome["algorithm_version"],
        "balance_version": outcome["balance_version"],
        "seed": outcome["seed"],
        "success": bool(outcome["success"]),
        "detected": bool(outcome["detected"]),
        "attacker_identified": identified,
        "attacker": {"name": attacker_name, "spies": int(attacker_spies)},
        "defender": {"name": defender_city.name},
    }

    if report_role == "attacker":
        # The attacker sees the auditable chances/rolls for its own mission but
        # never receives defender spy counts unless troop intel was actually
        # gathered. This prevents failed missions from leaking target defense.
        payload.update(
            {
                "luck": float(outcome["luck"]),
                "success_chance": float(outcome["success_chance"]),
                "success_roll": float(outcome["success_roll"]),
                "detection_chance": float(outcome["detection_chance"]),
                "detection_roll": float(outcome["detection_roll"]),
                "intel_level": int(outcome["intel_level"]),
                "revealed": [
                    key
                    for key, value in (
                        ("resources", resources),
                        ("troops", troops),
                        ("buildings", buildings),
                    )
                    if value is not None
                ],
                "resources": resources,
                "troops": troops,
                "buildings": buildings,
            }
        )
    else:
        payload.update(
            {
                "detection_chance": float(outcome["detection_chance"]),
                "defender_spies": int(defender_spies),
            }
        )

    return json.dumps(payload, sort_keys=True)


def resolve_spy(
    db: Session, movement: models.Movement
) -> Tuple[models.Report, models.Report | None, int]:
    """Resolve espionage without committing the caller's transaction.

    Mission success and defender detection are independent deterministic rolls.
    An undetected mission creates no defender report. On failure the dispatched
    spies are lost; a successful mission returns all dispatched spies.
    """

    attacker_city = movement.origin_city or (
        db.query(models.City).filter(models.City.id == movement.origin_city_id).first()
    )
    defender_city = movement.target_city or (
        db.query(models.City).filter(models.City.id == movement.target_city_id).first()
    )
    if not attacker_city or not defender_city:
        raise ValueError("Spy movement references a missing city")
    if attacker_city.world_id != movement.world_id or defender_city.world_id != movement.world_id:
        raise ValueError("Spy movement crosses world boundary")
    if attacker_city.id == defender_city.id:
        raise ValueError("A city cannot spy on itself")

    attacker_spies = int(movement.spy_count or 0)
    if attacker_spies <= 0:
        raise ValueError("Spy mission requires at least one spy")

    defender_spy_troop = (
        db.query(models.Troop)
        .filter(
            models.Troop.city_id == defender_city.id,
            models.Troop.unit_type == "spy",
        )
        .first()
    )
    defender_spies = int(defender_spy_troop.quantity) if defender_spy_troop else 0

    modifiers = event_service.get_active_modifiers(db, world_id=movement.world_id)
    spy_modifier = max(float(modifiers.get("spy_modifier", 1.0)), 0.0)
    seed = derive_seed(
        movement,
        attacker_spies=attacker_spies,
        defender_spies=defender_spies,
        spy_modifier=spy_modifier,
        defender_city=defender_city,
    )
    outcome = resolve_outcome(
        attacker_spies=attacker_spies,
        defender_spies=defender_spies,
        spy_modifier=spy_modifier,
        seed=seed,
    )

    intel_level = int(outcome["intel_level"])
    resources = None
    troops = None
    buildings = None
    if intel_level >= 1:
        resources = {
            resource: float(getattr(defender_city, resource))
            for resource in balance.RESOURCE_FIELDS
        }
    if intel_level >= 2:
        troops = {
            troop.unit_type: int(troop.quantity)
            for troop in defender_city.troops
            if int(troop.quantity) > 0
        }
    if intel_level >= 3 and balance.SPY_REVEALS_BUILDINGS_ON_SUCCESS:
        buildings = {
            building.name: int(building.level)
            for building in defender_city.buildings
            if int(building.level) > 0
        }

    attacker_report = models.Report(
        city_id=attacker_city.id,
        world_id=movement.world_id,
        report_type="spy",
        content=build_report_content(
            attacker_city=attacker_city,
            defender_city=defender_city,
            outcome=outcome,
            report_role="attacker",
            attacker_spies=attacker_spies,
            defender_spies=defender_spies,
            resources=resources,
            troops=troops,
            buildings=buildings,
        ),
        attacker_city_id=attacker_city.id,
        defender_city_id=defender_city.id,
    )
    db.add(attacker_report)

    defender_report: models.Report | None = None
    if bool(outcome["detected"]):
        defender_report = models.Report(
            city_id=defender_city.id,
            world_id=movement.world_id,
            report_type="spy",
            content=build_report_content(
                attacker_city=attacker_city,
                defender_city=defender_city,
                outcome=outcome,
                report_role="defender",
                attacker_spies=attacker_spies,
                defender_spies=defender_spies,
            ),
            attacker_city_id=attacker_city.id,
            defender_city_id=defender_city.id,
        )
        db.add(defender_report)

    surviving_spies = attacker_spies if bool(outcome["success"]) else 0
    return attacker_report, defender_report, surviving_spies

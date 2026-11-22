"""Authoritative, alliance-scoped, no-refund wonder escrow.

A single world row is locked before all target/project/donor rows, ensuring
contributions and building queue operations share one transaction order on
PostgreSQL. An old world's legacy rules never enter this service.
"""

from __future__ import annotations

from typing import Mapping

from sqlalchemy.orm import Session

from .. import models
from . import alliance as alliance_service
from . import balance, production, world_lifecycle

RESOURCE_FIELDS = balance.RESOURCE_FIELDS


def _int_amounts(amounts: Mapping[str, int]) -> dict[str, int]:
    values = {}
    for resource in RESOURCE_FIELDS:
        value = amounts.get(resource, 0)
        if type(value) is not int or value < 0:
            raise ValueError("Contributions must be nonnegative whole units")
        values[resource] = value
    if not any(values.values()):
        raise ValueError("At least one resource unit must be contributed")
    return values


def _project(db: Session, city: models.City, target_level: int, alliance_id: int):
    return db.query(models.WonderFunding).filter(
        models.WonderFunding.city_id == city.id,
        models.WonderFunding.world_id == city.world_id,
        models.WonderFunding.target_level == target_level,
        models.WonderFunding.owner_id == city.owner_id,
        models.WonderFunding.alliance_id == alliance_id,
    ).with_for_update().one_or_none()


def _member_alliance(
    db: Session, user_id: int, world_id: int, *, lock: bool = False,
) -> int | None:
    if lock:
        # A concurrent leave/kick must wait until an in-flight donation has
        # been charged and recorded, never revoke the membership mid-spend.
        membership = (
            db.query(models.AllianceMember)
            .join(models.Alliance, models.Alliance.id == models.AllianceMember.alliance_id)
            .filter(
                models.AllianceMember.user_id == user_id,
                models.Alliance.world_id == world_id,
            )
            .with_for_update(of=models.AllianceMember)
            .populate_existing()
            .one_or_none()
        )
    else:
        membership = alliance_service.get_membership_in_world(db, user_id, world_id)
    return membership.alliance_id if membership else None


def _requirements_met(city: models.City) -> bool:
    buildings = {entry.name: entry.level for entry in city.buildings}
    return all(
        buildings.get(name, 0) >= level
        for name, level in balance.BUILDING_PREREQUISITES["world_wonder"].items()
    )


def _snapshot(city: models.City, target_level: int, alliance_id: int | None, project=None) -> dict:
    rules = city.world.wonder_rules_version
    max_level = balance.get_building_max_level("world_wonder")
    if target_level > max_level:
        return {
            "world_id": city.world_id, "city_id": city.id, "target_level": max_level,
            "rules_version": rules, "alliance_id": alliance_id, "status": "completed",
            "cost": {}, "funded": {}, "remaining": {}, "can_queue": False,
            "build_time": 0,
        }
    cost = balance.get_wonder_cost(target_level, rules)
    funded = {
        res: int(getattr(project, f"funded_{res}")) if project else 0
        for res in RESOURCE_FIELDS
    }
    ready = project is not None and all(funded[res] == cost[res] for res in RESOURCE_FIELDS)
    return {
        "world_id": city.world_id,
        "city_id": city.id,
        "target_level": target_level,
        "rules_version": rules,
        "alliance_id": alliance_id,
        "status": project.status if project else "funding",
        "cost": cost,
        "funded": funded,
        "remaining": {res: cost[res] - funded[res] for res in RESOURCE_FIELDS},
        "can_queue": ready and project.status == "ready",
        "build_time": balance.get_wonder_build_time(target_level, rules),
    }


def get_funding(
    db: Session, city_id: int, world_id: int, user_id: int
) -> dict:
    """A player may read only a city owned by their world-alliance."""
    world = db.get(models.World, world_id)
    if world is None or world.wonder_rules_version != balance.WONDER_ALLIANCE_RULES:
        raise ValueError("Alliance wonder funding is unavailable in this world")
    city = db.query(models.City).filter(
        models.City.id == city_id,
        models.City.world_id == world_id,
        models.City.owner_id.isnot(None),
    ).one_or_none()
    if city is None or city.settlement_type != "city":
        raise ValueError("Wonder city not found")
    member = _member_alliance(db, user_id, world_id)
    owner_member = _member_alliance(db, city.owner_id, world_id)
    if member is None or member != owner_member:
        raise ValueError("Wonder city is not owned by your alliance")
    building = db.query(models.Building).filter_by(city_id=city.id, name="world_wonder").one_or_none()
    target_level = (building.level if building else 0) + 1
    project = _project(db, city, target_level, member)
    return _snapshot(city, target_level, member, project)


def contribute(
    db: Session,
    *,
    world_id: int,
    contributor_id: int,
    target_city_id: int,
    source_city_id: int,
    amounts: Mapping[str, int],
    idempotency_key: str,
) -> dict:
    amounts = _int_amounts(amounts)
    if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 80:
        raise ValueError("A unique 8-80 character idempotency key is required")
    try:
        world = world_lifecycle.require_world_open(db, world_id)
        if world.wonder_rules_version != balance.WONDER_ALLIANCE_RULES:
            raise ValueError("Legacy worlds use the original building rules")

        # Lock target before donor, the same order as queue_upgrade's world/city
        # locks. This serializes both first project creation and its final spend.
        city = db.query(models.City).filter_by(
            id=target_city_id, world_id=world_id,
        ).with_for_update().populate_existing().one_or_none()
        if city is None or city.owner_id is None or city.settlement_type != "city":
            raise ValueError("Wonder city not found")

        member = _member_alliance(db, contributor_id, world_id, lock=True)
        owner_member = _member_alliance(db, city.owner_id, world_id, lock=True)
        if member is None or member != owner_member:
            raise ValueError("Contributors and owner must belong to the same world alliance")
        if not _requirements_met(city):
            raise ValueError("Wonder building prerequisites are not met")

        donor = db.query(models.City).filter_by(
            id=source_city_id, world_id=world_id, owner_id=contributor_id,
        ).one_or_none()
        if donor is None:
            raise ValueError("Contribution source city not found")

        existing = db.query(models.WonderContribution).filter_by(
            world_id=world_id, contributor_id=contributor_id,
            idempotency_key=idempotency_key,
        ).one_or_none()
        if existing:
            original = {res: getattr(existing, res) for res in RESOURCE_FIELDS}
            project = db.get(models.WonderFunding, existing.funding_id)
            if (
                original != amounts
                or existing.source_city_id != source_city_id
                or project.city_id != target_city_id
                or project.owner_id != city.owner_id
                or project.alliance_id != member
            ):
                raise ValueError("Idempotency key was already used for a different contribution")
            response = _snapshot(city, project.target_level, member, project)
            db.rollback()  # End the read-only replay and release its row locks.
            return response

        building = db.query(models.Building).filter_by(
            city_id=city.id, name="world_wonder",
        ).with_for_update().one_or_none()
        target_level = (int(building.level) if building else 0) + 1
        if target_level > 100:
            raise ValueError("Wonder has reached maximum level")
        if db.query(models.BuildingQueue).filter_by(
            city_id=city.id, building_type="world_wonder",
        ).first():
            raise ValueError("Wonder upgrade already queued")

        project = _project(db, city, target_level, member)
        if not project:
            project = models.WonderFunding(
                city_id=city.id, world_id=world_id, owner_id=city.owner_id,
                alliance_id=member, target_level=target_level,
            )
            db.add(project)
            db.flush()
        if project.status != "funding":
            raise ValueError("Wonder is already fully funded or in progress")
        cost = balance.get_wonder_cost(target_level, world.wonder_rules_version)
        if any(getattr(project, f"funded_{res}") + val > cost[res] for res, val in amounts.items()):
            raise ValueError("Contribution exceeds the remaining requirement")

        donor, gains = production.lock_and_recalculate_resources(db, donor)
        if not production.check_cost(donor, amounts):
            raise ValueError("Insufficient resources in the contributor city")
        production.pay_cost(donor, amounts)
        for res, val in amounts.items():
            setattr(project, f"funded_{res}", getattr(project, f"funded_{res}") + val)
        if all(getattr(project, f"funded_{res}") == cost[res] for res in RESOURCE_FIELDS):
            project.status = "ready"
        db.add(models.WonderContribution(
            world_id=world_id, funding_id=project.id, contributor_id=contributor_id,
            source_city_id=source_city_id, idempotency_key=idempotency_key,
            **amounts,
        ))
        response = _snapshot(city, target_level, member, project)
        db.commit()
        production.record_resource_gains(db, donor, gains)
        return response
    except Exception:
        db.rollback()
        raise


def require_funded_project(db: Session, city: models.City, target_level: int) -> models.WonderFunding:
    alliance_id = _member_alliance(db, city.owner_id, city.world_id, lock=True)
    if alliance_id is None:
        raise ValueError("Wonder owner must be an active alliance member")
    project = _project(db, city, target_level, alliance_id)
    if project is None or project.status != "ready":
        raise ValueError("Wonder level requires complete alliance financing")
    cost = balance.get_wonder_cost(target_level, city.world.wonder_rules_version)
    if any(getattr(project, f"funded_{res}") != cost[res] for res in RESOURCE_FIELDS):
        raise ValueError("Incomplete wonder financing")
    return project


def restore_cancelled_project(db: Session, city: models.City, target_level: int) -> None:
    projects = db.query(models.WonderFunding).filter_by(
        city_id=city.id, target_level=target_level, status="queued",
    ).with_for_update().all()
    for project in projects:
        # No liquid refunds: escrow survives cancellation and can be reused
        # only by the same owner and alliance under the pinned world rules.
        project.status = "ready"


def queued_project_for_completion(
    db: Session, city: models.City, target_level: int,
) -> models.WonderFunding | None:
    """An authorized ledger, pinned to the same owner, must back each queue."""
    return db.query(models.WonderFunding).filter_by(
        city_id=city.id, world_id=city.world_id,
        target_level=target_level, owner_id=city.owner_id,
        status="queued",
    ).with_for_update().one_or_none()

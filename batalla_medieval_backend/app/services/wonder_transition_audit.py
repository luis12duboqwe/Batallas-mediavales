"""Read-only legacy Wonder migration impact assessment (BM-0062 / PD-009).

This module deliberately has NO conversion function, writes, locks or
administrative endpoint. A clean report is never authorization to change a
world's rules, owners, rankings or resource balances.
"""

from __future__ import annotations

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from .. import models
from . import balance, world_lifecycle


def audit_legacy_wonder_transition(db: Session, world_id: int) -> dict:
    """Return aggregate, non-PII evidence for a single pinned world.

    No autoflush, commit, update, deletion or mutation is permitted. Counts are
    scoped by world_id, including queues that store only their city_id.
    Results are a planning snapshot, not a concurrency-safe conversion gate.
    """
    if type(world_id) is not int or world_id < 1:
        raise ValueError("world_id must be a positive integer")

    with db.no_autoflush:
        world = db.get(models.World, world_id)
        if world is None:
            raise ValueError("World not found")

        players = db.query(func.count(models.PlayerWorld.id)).filter(
            models.PlayerWorld.world_id == world_id,
        ).scalar()
        legacy_user_links = db.query(func.count(models.User.id)).filter(
            models.User.world_id == world_id,
        ).scalar()
        # Legacy User.world_id may outlive the normalized PlayerWorld membership;
        # count missing memberships separately, never by subtracting totals.
        legacy_users_without_membership = (
            db.query(func.count(models.User.id))
            .outerjoin(
                models.PlayerWorld,
                and_(
                    models.PlayerWorld.user_id == models.User.id,
                    models.PlayerWorld.world_id == world_id,
                ),
            )
            .filter(
                models.User.world_id == world_id,
                models.PlayerWorld.id.is_(None),
            )
            .scalar()
        )
        city_count = db.query(func.count(models.City.id)).filter(
            models.City.world_id == world_id,
        ).scalar()
        owned_cities = db.query(func.count(models.City.id)).filter(
            models.City.world_id == world_id,
            models.City.owner_id.isnot(None),
        ).scalar()
        owned_cities_without_membership = (
            db.query(func.count(models.City.id))
            .outerjoin(
                models.PlayerWorld,
                and_(
                    models.PlayerWorld.user_id == models.City.owner_id,
                    models.PlayerWorld.world_id == models.City.world_id,
                ),
            )
            .filter(
                models.City.world_id == world_id,
                models.City.owner_id.isnot(None),
                models.PlayerWorld.id.is_(None),
            )
            .scalar()
        )
        alliances = db.query(func.count(models.Alliance.id)).filter(
            models.Alliance.world_id == world_id,
        ).scalar()
        alliance_members = (
            db.query(func.count(models.AllianceMember.id))
            .join(models.Alliance, models.Alliance.id == models.AllianceMember.alliance_id)
            .filter(models.Alliance.world_id == world_id)
            .scalar()
        )
        wonder_buildings = (
            db.query(func.count(models.Building.id))
            .join(models.City, models.City.id == models.Building.city_id)
            .filter(
                models.City.world_id == world_id,
                models.Building.name == "world_wonder",
            )
            .scalar()
        )
        max_wonder_level = (
            db.query(func.max(models.Building.level))
            .join(models.City, models.City.id == models.Building.city_id)
            .filter(
                models.City.world_id == world_id,
                models.Building.name == "world_wonder",
            )
            .scalar()
        )
        wonder_queues = (
            db.query(func.count(models.BuildingQueue.id))
            .join(models.City, models.City.id == models.BuildingQueue.city_id)
            .filter(
                models.City.world_id == world_id,
                models.BuildingQueue.building_type == "world_wonder",
            )
            .scalar()
        )
        funding_projects = db.query(func.count(models.WonderFunding.id)).filter(
            models.WonderFunding.world_id == world_id,
        ).scalar()
        contributions = db.query(func.count(models.WonderContribution.id)).filter(
            models.WonderContribution.world_id == world_id,
        ).scalar()

        status = world_lifecycle.status_of(world)
        blockers: list[str] = []
        if world.wonder_rules_version != balance.WONDER_LEGACY_RULES:
            blockers.append("NOT_LEGACY_RULES")
        if status != "paused":
            blockers.append("WORLD_NOT_PAUSED")
        if world.is_active is not False:
            blockers.append("WORLD_ACTIVE_FLAG")
        if world.ended_at is not None or world.winner_id is not None or world.winner_alliance_id is not None:
            blockers.append("WORLD_ALREADY_ENDED")
        if wonder_buildings:
            blockers.append("EXISTING_WONDER_LEVELS_REQUIRE_POLICY")
        if wonder_queues:
            blockers.append("PENDING_WONDER_QUEUE_REQUIRES_RECONCILIATION")
        if funding_projects or contributions:
            blockers.append("EXISTING_FUNDING_LEDGER_REQUIRES_RECONCILIATION")
        if players or legacy_user_links:
            blockers.append("PLAYER_CONSENT_NOT_VERIFIED")
        if legacy_users_without_membership:
            blockers.append("LEGACY_USER_LINK_WITHOUT_MEMBERSHIP")
        if owned_cities_without_membership:
            blockers.append("OWNED_CITIES_WITHOUT_MEMBERSHIP")
        if (players or legacy_user_links) and not alliance_members:
            blockers.append("ALLIANCE_SPONSOR_POLICY_REQUIRED")

        warehouse_limit = balance.get_storage_capacity(
            balance.get_building_max_level("warehouse")
        )
        legacy_cost = balance.get_wonder_cost(10, balance.WONDER_LEGACY_RULES)
        return {
            "world_id": world_id,
            "rules_version": world.wonder_rules_version,
            "lifecycle_status": status,
            "is_active": bool(world.is_active),
            "counts": {
                "players": int(players),
                "legacy_user_links": int(legacy_user_links),
                "legacy_user_links_without_membership": int(legacy_users_without_membership),
                "cities": int(city_count),
                "owned_cities": int(owned_cities),
                "owned_cities_without_membership": int(owned_cities_without_membership),
                "alliances": int(alliances),
                "alliance_members": int(alliance_members),
                "wonder_buildings": int(wonder_buildings),
                "highest_wonder_level": int(max_wonder_level or 0),
                "pending_wonder_queues": int(wonder_queues),
                "funding_projects": int(funding_projects),
                "contributions": int(contributions),
            },
            "legacy_level_10_cost": {
                resource: legacy_cost[resource] for resource in balance.RESOURCE_FIELDS
            },
            "max_warehouse_capacity_per_resource": warehouse_limit,
            "legacy_level_10_exceeds_storage": any(
                legacy_cost[resource] > warehouse_limit
                for resource in ("wood", "stone", "iron")
            ),
            "blockers": blockers,
            # Product approval, explicit player consent, a snapshot/rollback
            # and a controlled world pause are outside a read-only DB report.
            "requires_product_approval": True,
            "can_auto_convert": False,
        }

"""Prepare and validate the BM-0067 final PvE Browser G12 fixture."""

from __future__ import annotations

from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.seed import CANONICAL_BARBARIANS
from app.services import balance, pve, tutorial, world_membership
from app.utils import utc_now


USERNAME = "g12_pve"
PASSWORD = "G12-PvE-Test-2026!"
EMAIL = "g12-pve@example.com"
TARGET_COORD = CANONICAL_BARBARIANS[6]  # canonical tier 3


def _get_or_create_user(db) -> models.User:
    user = db.query(models.User).filter_by(username=USERNAME).one_or_none()
    if user is None:
        user = models.User(
            username=USERNAME,
            email=EMAIL,
            hashed_password=get_password_hash(PASSWORD),
            is_verified=True,
            protection_ends_at=utc_now() - timedelta(hours=1),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = EMAIL
        user.hashed_password = get_password_hash(PASSWORD)
        user.is_verified = True
        user.protection_ends_at = utc_now() - timedelta(hours=1)
        db.add(user)
        db.commit()
    return user


def main() -> None:
    db = SessionLocal()
    try:
        world = (
            db.query(models.World)
            .filter(models.World.is_active.is_(True))
            .order_by(models.World.id.asc())
            .first()
        )
        if world is None:
            raise RuntimeError("Canonical seed did not create an active world")

        user = _get_or_create_user(db)
        world_membership.join_world(db, user, world.id)
        user.tutorial_step = tutorial.FINAL_STEP
        user.tutorial_reward_claimed = True
        db.add(user)

        pve.ensure_world_pve(
            db,
            world,
            canonical_barbarian_coords=CANONICAL_BARBARIANS,
        )
        db.commit()
        db.expire_all()

        world = db.query(models.World).filter_by(id=world.id).one()
        if pve.world_rules_version(world) != pve.PVE_RULES_VERSION:
            raise RuntimeError("G12 world is not pinned to BM-0067 rules")

        target_x, target_y = TARGET_COORD
        barbarian = (
            db.query(models.City)
            .filter_by(world_id=world.id, x=target_x, y=target_y)
            .one()
        )
        if barbarian.owner_id is not None:
            raise RuntimeError("G12 tier-3 barbarian was unexpectedly conquered")
        if pve.barbarian_tier(barbarian) != 3:
            raise RuntimeError("G12 canonical barbarian is not tier 3")

        profile = pve.BARBARIAN_PROFILES[3]
        troops = {troop.unit_type: troop.quantity for troop in barbarian.troops}
        buildings = {building.name: building.level for building in barbarian.buildings}
        if troops != profile["troops"] or buildings != profile["buildings"]:
            raise RuntimeError(
                f"G12 tier-3 barbarian profile mismatch: troops={troops} buildings={buildings}"
            )

        oasis = (
            db.query(models.Oasis)
            .filter(
                models.Oasis.world_id == world.id,
                models.Oasis.owner_city_id.is_(None),
            )
            .order_by(models.Oasis.id.asc())
            .first()
        )
        if oasis is None:
            raise RuntimeError("G12 world has no wild oasis")
        oasis_tier = pve.oasis_tier(oasis)
        oasis_profile = pve.OASIS_PROFILES[oasis_tier]
        if oasis.troops != oasis_profile["guards"]:
            raise RuntimeError(f"G12 oasis guards mismatch: {oasis.troops}")
        if not oasis.troops or not set(oasis.troops).issubset(balance.UNIT_COMBAT_STATS):
            raise RuntimeError(f"G12 oasis contains non-canonical guards: {oasis.troops}")
        if oasis.bonus_percent != oasis_profile["bonus_percent"]:
            raise RuntimeError("G12 oasis bonus does not match its tier")

        active_barbarians = (
            db.query(models.City)
            .filter(
                models.City.world_id == world.id,
                models.City.owner_id.is_(None),
            )
            .count()
        )
        oasis_count = db.query(models.Oasis).filter_by(world_id=world.id).count()
        if active_barbarians != pve.PVE_BARBARIAN_TARGET_ACTIVE:
            raise RuntimeError(f"G12 barbarian population mismatch: {active_barbarians}")
        if oasis_count != pve.PVE_OASIS_TARGET_TOTAL:
            raise RuntimeError(f"G12 oasis population mismatch: {oasis_count}")

        print(
            "prepared-g12:"
            f"{user.id}:{world.id}:"
            f"barbarian={barbarian.id}@{target_x},{target_y}:tier=3:"
            f"oasis={oasis.id}@{oasis.x},{oasis.y}:tier={oasis_tier}:"
            f"rules={pve.PVE_RULES_VERSION}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

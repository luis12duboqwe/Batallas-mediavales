"""Prepare deterministic BM-0072 world lifecycle Browser G16 fixtures."""

from __future__ import annotations

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import tutorial, world_membership

PASSWORD = "G16-Lifecycle-Test-2026!"
ADMIN_USERNAME = "g16_admin"
PLAYER_USERNAME = "g16_player"
WORLD_NAME = "G16 Lifecycle World"


def _user(db, username: str, email: str, *, is_admin: bool = False) -> models.User:
    row = db.query(models.User).filter_by(username=username).one_or_none()
    if row is None:
        row = models.User(
            username=username,
            email=email,
            hashed_password=get_password_hash(PASSWORD),
            is_verified=True,
            is_admin=is_admin,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        row.email = email
        row.hashed_password = get_password_hash(PASSWORD)
        row.is_verified = True
        row.is_admin = is_admin
        db.add(row)
        db.commit()
    return row


def main() -> None:
    db = SessionLocal()
    try:
        canonical = (
            db.query(models.World)
            .filter(models.World.lifecycle_status == "open")
            .order_by(models.World.id.asc())
            .first()
        )
        if canonical is None:
            raise RuntimeError("Canonical seed did not create an open world")

        admin = _user(db, ADMIN_USERNAME, "g16-admin@example.com", is_admin=True)
        player = _user(db, PLAYER_USERNAME, "g16-player@example.com")

        # Keep admin layout/store hydration stable while the dedicated lifecycle
        # world remains draft.
        world_membership.join_world(db, admin, canonical.id)
        admin.tutorial_step = tutorial.FINAL_STEP
        admin.tutorial_reward_claimed = True
        player.tutorial_step = tutorial.FINAL_STEP
        player.tutorial_reward_claimed = True
        db.add_all([admin, player])

        world = db.query(models.World).filter_by(name=WORLD_NAME).one_or_none()
        if world is None:
            world = models.World(
                name=WORLD_NAME,
                speed_modifier=1.0,
                resource_modifier=1.0,
                map_size=25,
                special_rules="BM-0072 lifecycle E2E fixture",
                is_active=False,
                lifecycle_status="draft",
            )
            db.add(world)
            db.flush()
        else:
            # Remove only G16 player's prior fixture state for retry-safe CI
            # preparation. Never delete arbitrary game data.
            membership = (
                db.query(models.PlayerWorld)
                .filter_by(user_id=player.id, world_id=world.id)
                .one_or_none()
            )
            if membership is not None:
                if membership.starting_city_id is not None:
                    city = db.query(models.City).filter_by(id=membership.starting_city_id).one_or_none()
                    if city is not None:
                        db.delete(city)
                db.delete(membership)
                db.flush()
            world.lifecycle_status = "draft"
            world.is_active = False
            world.pause_started_at = None
            world.ended_at = None
            world.winner_id = None
            world.winner_alliance_id = None

        if player.world_id == world.id:
            player.world_id = None
        db.add_all([world, player])
        db.commit()
        db.refresh(world)
        print(f"prepared-g16:world={world.id}:admin={admin.id}:player={player.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""Prepare only a disposable loopback test world for Wonder browser E2E."""
import os
from pathlib import Path
from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import world_gen, world_membership
from app.utils import utc_now

def main():
    file = os.environ.get("PARALLEL_JOURNEY_DB")
    url = os.environ.get("DATABASE_URL")
    if not file or (
        os.environ.get("APP_ENV") != "test"
        or os.environ.get("PARALLEL_JOURNEY_ALLOW_MUTATIONS") != "isolated"
        or not Path(file).resolve().as_posix().startswith("/tmp/medievol-journey-")
        or url != "sqlite:///" + str(Path(file).resolve())
    ):
        raise RuntimeError("Only disposable /tmp isolated test SQLite is authorized")
    db = SessionLocal()
    try:
        world = db.query(models.World).filter_by(lifecycle_status="open").order_by(models.World.id).first()
        if world is None or world.wonder_rules_version != "alliance-v2":
            raise RuntimeError("Test world does not pin alliance-v2")
        owner = db.query(models.User).filter_by(username="g2_browser").one()
        donor = db.query(models.User).filter_by(username="g9_combat").one()
        target_city = db.query(models.City).filter_by(owner_id=owner.id, world_id=world.id).order_by(models.City.id).first()
        donor_city = db.query(models.City).filter_by(owner_id=donor.id, world_id=world.id).order_by(models.City.id).first()
        if not target_city or not donor_city or target_city.id == donor_city.id:
            raise RuntimeError("Different fixture cities required")
        alliance = models.Alliance(name="Wonder Isolated E2E Alliance", world_id=world.id, leader_id=owner.id)
        db.add(alliance)
        db.flush()
        db.add_all([
            models.AllianceMember(alliance_id=alliance.id, user_id=owner.id, rank=3),
            models.AllianceMember(alliance_id=alliance.id, user_id=donor.id, rank=1),
        ])
        for name, level in (("town_hall", 20), ("warehouse", 20), ("cathedral", 10)):
            row = db.query(models.Building).filter_by(city_id=target_city.id, name=name).one_or_none()
            if row is None:
                db.add(models.Building(city_id=target_city.id, name=name, level=level))
            else:
                row.level = level
        for city in (target_city, donor_city):
            for res in ("wood", "stone", "iron", "gold"):
                setattr(city, res, 45000.0)
        db.commit()

        # Negative and historical-world journeys use only disposable users.
        # Keep the fixture data separate from the two real-browser donors.
        credentials = (
            ("wonder_stranger", "Wonder-Stranger-Test-2026!"),
            ("wonder_enemy", "Wonder-Enemy-Test-2026!"),
            ("wonder_legacy", "Wonder-Legacy-Test-2026!"),
            ("wonder_legacy_ally", "Wonder-Legacy-Ally-Test-2026!"),
        )
        users = {}
        for username, password in credentials:
            if db.query(models.User).filter_by(username=username).first():
                raise RuntimeError("Refusing to reuse Wonder E2E account")
            account = models.User(
                username=username,
                email=f"{username}@example.invalid",
                hashed_password=get_password_hash(password),
                is_verified=True,
            )
            db.add(account)
            users[username] = account
        db.flush()

        # A same-world player without any alliance must never load the
        # restricted funding panel or issue a funding GET.
        world_membership.join_world(db, users["wonder_stranger"], world.id)

        # A different alliance has its own owned city, but cannot finance
        # or read the owner's project.
        world_membership.join_world(db, users["wonder_enemy"], world.id)
        rival = models.Alliance(
            name="Wonder Rival E2E", world_id=world.id,
            leader_id=users["wonder_enemy"].id,
        )
        db.add(rival)
        db.flush()
        db.add(models.AllianceMember(
            alliance_id=rival.id, user_id=users["wonder_enemy"].id, rank=3,
        ))

        # A valid donor's second city has no resources: the API must refuse
        # to charge it without affecting balances or the funding ledger.
        poor_x, poor_y = world_gen.find_spawn_location(db, world.id, world.map_size)
        poor_city = models.City(
            name="Wonder Empty Test City", owner_id=donor.id, world_id=world.id,
            x=poor_x, y=poor_y, wood=0.0, stone=0.0, iron=0.0, gold=0.0,
            last_production=utc_now(),
        )
        db.add(poor_city)

        # Explicitly versioned legacy world with two genuine alliance members,
        # so its map can prove that even an allied city has no funding CTA.
        legacy_world = models.World(
            name="Wonder Legacy E2E", map_size=100,
            is_active=True, lifecycle_status="open",
            wonder_rules_version="legacy-v1",
        )
        db.add(legacy_world)
        db.flush()
        world_membership.join_world(db, users["wonder_legacy"], legacy_world.id)
        world_membership.join_world(db, users["wonder_legacy_ally"], legacy_world.id)
        legacy_alliance = models.Alliance(
            name="Wonder Legacy E2E Alliance", world_id=legacy_world.id,
            leader_id=users["wonder_legacy"].id,
        )
        db.add(legacy_alliance)
        db.flush()
        db.add_all((
            models.AllianceMember(
                alliance_id=legacy_alliance.id,
                user_id=users["wonder_legacy"].id, rank=3,
            ),
            models.AllianceMember(
                alliance_id=legacy_alliance.id,
                user_id=users["wonder_legacy_ally"].id, rank=1,
            ),
        ))
        db.commit()
        print(
            f"WONDER_BROWSER_FIXTURE world={world.id} target={target_city.id} "
            f"donor={donor_city.id} legacy={legacy_world.id} poor={poor_city.id}"
        )
    finally:
        db.close()

if __name__ == "__main__":
    main()

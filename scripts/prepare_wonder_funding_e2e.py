"""Prepare only a disposable loopback test world for Wonder browser E2E."""
import os
from pathlib import Path
from app import models
from app.database import SessionLocal

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
        print(f"WONDER_BROWSER_FIXTURE world={world.id} target={target_city.id} donor={donor_city.id}")
    finally:
        db.close()

if __name__ == "__main__":
    main()

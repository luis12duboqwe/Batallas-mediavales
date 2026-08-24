"""Prepare deterministic research state for the BM-0062 browser journey."""

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import balance, world_membership
from app.utils import utc_now


USERNAME = "g7_research"
PASSWORD = "G7-Research-Test-2026!"
EMAIL = "g7-research@example.com"
TECH_NAME = "heavy_infantry"


def _set_resources(city: models.City, amount: float) -> None:
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, amount)
    city.last_production = utc_now()


def _set_building(db, city_id: int, name: str, level: int) -> None:
    row = (
        db.query(models.Building)
        .filter_by(city_id=city_id, name=name)
        .one_or_none()
    )
    if row is None:
        row = models.Building(city_id=city_id, name=name, level=level)
    else:
        row.level = level
    db.add(row)


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

        user = db.query(models.User).filter_by(username=USERNAME).one_or_none()
        if user is None:
            user = models.User(
                username=USERNAME,
                email=EMAIL,
                hashed_password=get_password_hash(PASSWORD),
                is_verified=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.email = EMAIL
            user.hashed_password = get_password_hash(PASSWORD)
            user.is_verified = True
            db.add(user)
            db.commit()

        world_membership.join_world(db, user, world.id)
        membership = (
            db.query(models.PlayerWorld)
            .filter_by(user_id=user.id, world_id=world.id)
            .one()
        )
        city = (
            db.query(models.City)
            .filter_by(id=membership.starting_city_id, owner_id=user.id)
            .one()
        )

        db.query(models.ResearchQueue).filter_by(city_id=city.id).delete(
            synchronize_session=False
        )
        db.query(models.Research).filter_by(
            city_id=city.id,
            tech_name=TECH_NAME,
        ).delete(synchronize_session=False)
        city.researched_units = [
            unit for unit in list(city.researched_units or []) if unit != TECH_NAME
        ]
        if "basic_infantry" not in city.researched_units:
            city.researched_units.insert(0, "basic_infantry")

        _set_building(db, city.id, "town_hall", 4)
        _set_building(db, city.id, "barracks", 3)
        _set_building(db, city.id, "academy", 1)
        _set_building(db, city.id, "smithy", 1)
        _set_resources(city, 5000.0)
        db.add(city)
        db.commit()

        print(
            f"prepared-g7:{user.id}:{world.id}:{city.id}:academy=1:barracks=3"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

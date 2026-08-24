"""Prepare deterministic unit/upkeep state for the BM-0063 browser journey."""

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import balance, world_membership
from app.utils import utc_now


USERNAME = "g8_upkeep"
PASSWORD = "G8-Upkeep-Test-2026!"
EMAIL = "g8-upkeep@example.com"
UNIT_TYPE = "noble"
STARTING_RESOURCE_AMOUNT = 4000.0


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

        # The journey must begin with no population/upkeep reservations so the
        # observed headroom comes entirely from the canonical BM-0063 balance.
        db.query(models.TroopQueue).filter_by(city_id=city.id).delete(
            synchronize_session=False
        )
        db.query(models.Troop).filter_by(city_id=city.id).delete(
            synchronize_session=False
        )
        db.query(models.Movement).filter(
            models.Movement.world_id == world.id,
            (models.Movement.origin_city_id == city.id)
            | (models.Movement.target_city_id == city.id),
        ).delete(synchronize_session=False)

        _set_building(db, city.id, "town_hall", 20)
        _set_building(db, city.id, "workshop", 10)

        research = (
            db.query(models.Research)
            .filter_by(city_id=city.id, tech_name=UNIT_TYPE)
            .one_or_none()
        )
        if research is None:
            db.add(models.Research(city_id=city.id, tech_name=UNIT_TYPE, level=1))

        city.researched_units = ["basic_infantry", UNIT_TYPE]
        city.population_max = 100
        _set_resources(city, STARTING_RESOURCE_AMOUNT)
        db.add(city)
        db.commit()

        definition = balance.UNIT_CATALOG[UNIT_TYPE]
        capacity = balance.PRODUCTION_RATES_PER_HOUR["gold"] * float(
            world.resource_modifier or 0.0
        )
        print(
            "prepared-g8:"
            f"{user.id}:{world.id}:{city.id}:"
            f"unit={UNIT_TYPE}:population={definition['population']}:"
            f"upkeep={definition['upkeep_per_hour']}:capacity={capacity:g}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

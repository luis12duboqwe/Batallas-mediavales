"""Prepare deterministic expansion state for the G6 browser journey."""

from app import models
from app.database import SessionLocal
from app.services import balance, world_gen
from app.utils import utc_now


USERNAME = "g2_browser"
CAMP_NAME = "G6 Promotion Camp"


def _set_resources(city: models.City, amount: float) -> None:
    for resource in balance.RESOURCE_FIELDS:
        setattr(city, resource, amount)
    city.last_production = utc_now()


def main() -> None:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(username=USERNAME).one()
        membership = (
            db.query(models.PlayerWorld)
            .filter_by(user_id=user.id, world_id=user.world_id)
            .one()
        )
        capital = (
            db.query(models.City)
            .filter_by(id=membership.starting_city_id, owner_id=user.id)
            .one()
        )

        membership.expansion_points = 5
        _set_resources(capital, 5000.0)

        camp = (
            db.query(models.City)
            .filter_by(
                owner_id=user.id,
                world_id=user.world_id,
                name=CAMP_NAME,
            )
            .one_or_none()
        )
        if camp is None:
            world = db.query(models.World).filter_by(id=user.world_id).one()
            x, y = world_gen.find_spawn_location(db, world.id, world.map_size)
            camp = models.City(
                name=CAMP_NAME,
                owner_id=user.id,
                world_id=world.id,
                x=x,
                y=y,
                settlement_type="camp",
                population_max=balance.CAMP_POPULATION_MAX,
                tile_type=world_gen.get_tile_type(x, y),
            )
            db.add(camp)
            db.flush()
            for definition in balance.CAMP_STARTER_BUILDINGS:
                db.add(
                    models.Building(
                        city_id=camp.id,
                        name=definition["name"],
                        level=definition["level"],
                    )
                )
        else:
            camp.settlement_type = "camp"
            camp.population_max = balance.CAMP_POPULATION_MAX

        _set_resources(camp, 5000.0)
        db.add_all([membership, capital, camp])
        db.commit()
        print(
            f"prepared-g6:{user.id}:{user.world_id}:{capital.id}:{camp.id}:points={membership.expansion_points}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""Prepare and resolve one auditable BM-0064 battle for Browser G9."""

from __future__ import annotations

import json
from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import combat, movement, tutorial, world_membership
from app.utils import utc_now


USERNAME = "g9_combat"
PASSWORD = "G9-Combat-Test-2026!"
EMAIL = "g9-combat@example.com"


def _free_city_coordinate(db, world: models.World) -> tuple[int, int]:
    occupied = {
        (int(x), int(y))
        for x, y in db.query(models.City.x, models.City.y)
        .filter(models.City.world_id == world.id)
        .all()
    }
    map_size = max(int(world.map_size), 1)
    for y in range(map_size):
        for x in range(map_size):
            if (x, y) not in occupied:
                return x, y
    raise RuntimeError("G9 world has no free city coordinate")


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
        user.tutorial_step = tutorial.FINAL_STEP
        user.tutorial_reward_claimed = True
        db.add(user)

        # Make the fixture idempotent when run manually against a reused DB.
        db.query(models.Report).filter_by(city_id=city.id, world_id=world.id).delete(
            synchronize_session=False
        )
        db.query(models.Movement).filter(
            models.Movement.world_id == world.id,
            (
                (models.Movement.origin_city_id == city.id)
                | (models.Movement.target_city_id == city.id)
            ),
        ).delete(synchronize_session=False)
        db.query(models.Troop).filter_by(city_id=city.id).delete(
            synchronize_session=False
        )

        target = (
            db.query(models.City)
            .filter_by(name="G9 Auditable Barbarian", world_id=world.id)
            .one_or_none()
        )
        if target is None:
            target_x, target_y = _free_city_coordinate(db, world)
            target = models.City(
                name="G9 Auditable Barbarian",
                owner_id=None,
                world_id=world.id,
                x=target_x,
                y=target_y,
                wood=1400.0,
                stone=1200.0,
                iron=1000.0,
                gold=800.0,
            )
            db.add(target)
            db.flush()
        else:
            target.owner_id = None
            target.loyalty = 100.0
            target.wood = 1400.0
            target.stone = 1200.0
            target.iron = 1000.0
            target.gold = 800.0
            db.query(models.Troop).filter_by(city_id=target.id).delete(
                synchronize_session=False
            )

        db.add_all(
            [
                models.Troop(
                    city_id=target.id,
                    unit_type="basic_infantry",
                    quantity=35,
                ),
                models.Troop(
                    city_id=target.id,
                    unit_type="archer",
                    quantity=15,
                ),
            ]
        )
        attack = models.Movement(
            origin_city_id=city.id,
            target_city_id=target.id,
            world_id=world.id,
            movement_type="attack",
            troops={"heavy_cavalry": 70, "archer": 30},
            resources={},
            spy_count=0,
            arrival_time=utc_now() - timedelta(seconds=1),
            speed_used=1.0,
            status="ongoing",
        )
        db.add(attack)
        db.commit()

        processed = movement.resolve_due_movements(db)
        if attack.id not in processed:
            raise RuntimeError(f"G9 attack was not resolved exactly once: {processed}")

        report = (
            db.query(models.Report)
            .filter_by(
                city_id=city.id,
                attacker_city_id=city.id,
                defender_city_id=target.id,
                report_type="battle",
            )
            .order_by(models.Report.id.desc())
            .first()
        )
        if report is None:
            raise RuntimeError("G9 resolution did not create attacker battle report")
        payload = json.loads(str(report.content))
        audit = payload.get("combat") or {}
        if audit.get("algorithm_version") != combat.COMBAT_ALGORITHM_VERSION:
            raise RuntimeError(f"Unexpected combat algorithm: {audit}")
        if not audit.get("seed"):
            raise RuntimeError("G9 report has no auditable seed")
        if not 1 <= int(audit.get("round_count") or 0) <= combat.COMBAT_MAX_ROUNDS:
            raise RuntimeError(f"G9 report has invalid round count: {audit}")

        return_march = (
            db.query(models.Movement)
            .filter_by(
                target_city_id=city.id,
                world_id=world.id,
                movement_type="return",
                status="ongoing",
            )
            .order_by(models.Movement.id.desc())
            .first()
        )
        if return_march is None:
            raise RuntimeError("G9 resolution did not create a return march")

        # A retry after the committed resolution must not reroll or duplicate it.
        if movement.resolve_due_movements(db):
            raise RuntimeError("G9 retry unexpectedly processed another due movement")
        report_count = (
            db.query(models.Report)
            .filter_by(
                city_id=city.id,
                attacker_city_id=city.id,
                defender_city_id=target.id,
                report_type="battle",
            )
            .count()
        )
        return_count = (
            db.query(models.Movement)
            .filter_by(
                target_city_id=city.id,
                world_id=world.id,
                movement_type="return",
                status="ongoing",
            )
            .count()
        )
        if report_count != 1 or return_count != 1:
            raise RuntimeError(
                f"G9 retry duplicated state: reports={report_count} returns={return_count}"
            )

        print(
            "prepared-g9:"
            f"{user.id}:{world.id}:{city.id}:{target.id}:"
            f"seed={audit['seed']}:rounds={audit['round_count']}:"
            f"outcome={audit.get('outcome')}:return={return_march.id}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

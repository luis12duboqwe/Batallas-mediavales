"""Prepare one deterministic, auditable BM-0065 espionage mission for Browser G10."""

from __future__ import annotations

import json
from datetime import timedelta

from app import models
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import espionage, event as event_service, movement, tutorial, world_membership
from app.utils import utc_now


USERNAME = "g10_espionage"
PASSWORD = "G10-Espionage-Test-2026!"
EMAIL = "g10-espionage@example.com"
DEFENDER_USERNAME = "g10_spy_target"


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
    raise RuntimeError("G10 world has no free city coordinate")


def _get_or_create_user(db, *, username: str, email: str, password: str) -> models.User:
    user = db.query(models.User).filter_by(username=username).one_or_none()
    if user is None:
        user = models.User(
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            is_verified=True,
            protection_ends_at=utc_now() - timedelta(hours=1),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = email
        user.hashed_password = get_password_hash(password)
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

        user = _get_or_create_user(
            db,
            username=USERNAME,
            email=EMAIL,
            password=PASSWORD,
        )
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

        defender = _get_or_create_user(
            db,
            username=DEFENDER_USERNAME,
            email="g10-spy-target@example.com",
            password="G10-Target-Only-2026!",
        )
        target = (
            db.query(models.City)
            .filter_by(name="G10 Intelligence Target", world_id=world.id)
            .one_or_none()
        )
        if target is None:
            target_x, target_y = _free_city_coordinate(db, world)
            target = models.City(
                name="G10 Intelligence Target",
                owner_id=defender.id,
                world_id=world.id,
                x=target_x,
                y=target_y,
                wood=1234.0,
                stone=987.0,
                iron=765.0,
                gold=543.0,
                last_production=utc_now(),
            )
            db.add(target)
            db.flush()
        else:
            target.owner_id = defender.id
            target.wood = 1234.0
            target.stone = 987.0
            target.iron = 765.0
            target.gold = 543.0
            target.last_production = utc_now()

        # Keep the fixture idempotent when rerun manually.
        db.query(models.Report).filter(
            models.Report.world_id == world.id,
            (
                (models.Report.city_id == city.id)
                | (models.Report.city_id == target.id)
            ),
        ).delete(synchronize_session=False)
        db.query(models.Movement).filter(
            models.Movement.world_id == world.id,
            (
                (models.Movement.origin_city_id == city.id)
                | (models.Movement.target_city_id == city.id)
                | (models.Movement.origin_city_id == target.id)
                | (models.Movement.target_city_id == target.id)
            ),
        ).delete(synchronize_session=False)
        db.query(models.Troop).filter_by(city_id=target.id).delete(
            synchronize_session=False
        )
        db.query(models.Building).filter_by(city_id=target.id).delete(
            synchronize_session=False
        )
        db.add_all(
            [
                models.Troop(city_id=target.id, unit_type="archer", quantity=9),
                models.Building(city_id=target.id, name="wall", level=3),
            ]
        )

        spy_movement = models.Movement(
            origin_city_id=city.id,
            target_city_id=target.id,
            world_id=world.id,
            movement_type="spy",
            troops={},
            resources={},
            spy_count=6,
            arrival_time=utc_now() - timedelta(seconds=1),
            speed_used=1.0,
            status="ongoing",
        )
        db.add(spy_movement)
        db.flush()

        # Choose a target pre-state whose real BM-0065 seed produces the desired
        # accepted journey: success, level-3 intel, and no defender detection.
        modifiers = event_service.get_active_modifiers(db, world_id=world.id)
        spy_modifier = max(float(modifiers.get("spy_modifier", 1.0)), 0.0)
        selected = None
        for offset in range(200):
            target.gold = 543.0 + offset
            db.add(target)
            db.flush()
            seed = espionage.derive_seed(
                spy_movement,
                attacker_spies=6,
                defender_spies=0,
                spy_modifier=spy_modifier,
                defender_city=target,
            )
            outcome = espionage.resolve_outcome(
                attacker_spies=6,
                defender_spies=0,
                spy_modifier=spy_modifier,
                seed=seed,
            )
            if outcome["success"] and not outcome["detected"] and outcome["intel_level"] == 3:
                selected = outcome
                break
        if selected is None:
            raise RuntimeError("Could not prepare deterministic G10 espionage outcome")

        db.commit()
        processed = movement.resolve_due_movements(db)
        if [item.id for item in processed] != [spy_movement.id]:
            raise RuntimeError(f"G10 spy movement was not resolved exactly once: {[item.id for item in processed]}")

        attacker_report = (
            db.query(models.Report)
            .filter_by(
                city_id=city.id,
                attacker_city_id=city.id,
                defender_city_id=target.id,
                report_type="spy",
            )
            .one_or_none()
        )
        if attacker_report is None:
            raise RuntimeError("G10 did not create attacker spy report")
        payload = json.loads(str(attacker_report.content))
        if payload.get("algorithm_version") != espionage.ESPIONAGE_ALGORITHM_VERSION:
            raise RuntimeError(f"Unexpected espionage algorithm: {payload}")
        if payload.get("seed") != selected["seed"]:
            raise RuntimeError("G10 report seed does not match resolved outcome")
        if payload.get("success") is not True or payload.get("detected") is not False:
            raise RuntimeError(f"Unexpected G10 success/detection result: {payload}")
        if int(payload.get("intel_level") or 0) != 3:
            raise RuntimeError(f"Unexpected G10 intelligence level: {payload}")
        if payload.get("revealed") != ["resources", "troops", "buildings"]:
            raise RuntimeError(f"G10 report did not reveal tier-3 intelligence: {payload}")
        if payload.get("troops", {}).get("archer") != 9:
            raise RuntimeError(f"G10 troop intelligence mismatch: {payload}")
        if payload.get("buildings", {}).get("wall") != 3:
            raise RuntimeError(f"G10 building intelligence mismatch: {payload}")

        defender_reports = (
            db.query(models.Report)
            .filter_by(
                city_id=target.id,
                attacker_city_id=city.id,
                defender_city_id=target.id,
                report_type="spy",
            )
            .count()
        )
        if defender_reports != 0:
            raise RuntimeError(f"Undetected G10 mission leaked defender report: {defender_reports}")

        return_march = (
            db.query(models.Movement)
            .filter_by(
                target_city_id=city.id,
                world_id=world.id,
                movement_type="return",
                status="ongoing",
            )
            .one_or_none()
        )
        if return_march is None or return_march.troops != {"spy": 6}:
            raise RuntimeError(f"G10 spy return mismatch: {return_march}")

        # A retry must not reroll, create a second report, or duplicate returns.
        if movement.resolve_due_movements(db):
            raise RuntimeError("G10 retry unexpectedly processed another due movement")
        report_count = (
            db.query(models.Report)
            .filter_by(city_id=city.id, report_type="spy")
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
                f"G10 retry duplicated state: reports={report_count} returns={return_count}"
            )

        print(
            "prepared-g10:"
            f"{user.id}:{world.id}:{city.id}:{target.id}:"
            f"seed={payload['seed']}:intel={payload['intel_level']}:"
            f"detected={payload['detected']}:return={return_march.id}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

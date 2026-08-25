"""Prepare an auditable BM-0066 commerce lifecycle for Browser G11."""

from __future__ import annotations

import json
from datetime import timedelta

from app import models, schemas
from app.database import SessionLocal
from app.routers.auth import get_password_hash
from app.services import balance, market, movement, tutorial, world_membership
from app.utils import utc_now


USERNAME = "g11_commerce"
PASSWORD = "G11-Commerce-Test-2026!"
EMAIL = "g11-commerce@example.com"
TARGET_USERNAME = "g11_commerce_target"


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
    raise RuntimeError("G11 world has no free city coordinate")


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

        target_user = _get_or_create_user(
            db,
            username=TARGET_USERNAME,
            email="g11-commerce-target@example.com",
            password="G11-Target-Only-2026!",
        )
        target = (
            db.query(models.City)
            .filter_by(name="G11 Storage Target", world_id=world.id)
            .one_or_none()
        )
        if target is None:
            target_x, target_y = _free_city_coordinate(db, world)
            target = models.City(
                name="G11 Storage Target",
                owner_id=target_user.id,
                world_id=world.id,
                x=target_x,
                y=target_y,
                wood=4950.0,
                stone=1000.0,
                iron=1000.0,
                gold=1000.0,
                last_production=utc_now(),
            )
            db.add(target)
            db.flush()
        else:
            target.owner_id = target_user.id
            target.wood = 4950.0
            target.stone = 1000.0
            target.iron = 1000.0
            target.gold = 1000.0
            target.last_production = utc_now()

        # Keep the starting city genuinely market-less: BM-0066 commerce must
        # work from the first session and the building is only an expansion.
        db.query(models.Building).filter_by(city_id=city.id, name="market").delete(
            synchronize_session=False
        )
        # The destination uses the base 5000 storage cap for the rejection case.
        db.query(models.Building).filter_by(city_id=target.id, name="warehouse").delete(
            synchronize_session=False
        )

        db.query(models.MarketOffer).filter(
            models.MarketOffer.world_id == world.id,
            models.MarketOffer.city_id.in_([city.id, target.id]),
        ).delete(synchronize_session=False)
        db.query(models.Report).filter(
            models.Report.world_id == world.id,
            models.Report.city_id.in_([city.id, target.id]),
        ).delete(synchronize_session=False)
        db.query(models.Movement).filter(
            models.Movement.world_id == world.id,
            (
                models.Movement.origin_city_id.in_([city.id, target.id])
                | models.Movement.target_city_id.in_([city.id, target.id])
            ),
        ).delete(synchronize_session=False)

        city.wood = 1000.0
        city.stone = 1000.0
        city.iron = 1000.0
        city.gold = 1000.0
        city.last_production = utc_now()
        db.add_all([city, target])
        db.commit()
        db.expire(city, ["buildings"])
        db.expire(target, ["buildings"])

        rules = market.commerce_rules_snapshot()
        if rules.get("rules_version") != balance.COMMERCE_RULES_VERSION:
            raise RuntimeError(f"G11 commerce rules version mismatch: {rules}")
        if market._get_market_capacity(city) != balance.BASE_MERCHANT_CAPACITY:
            raise RuntimeError("G11 city does not have start-of-world merchant capacity")
        if any(building.name == "market" for building in city.buildings):
            raise RuntimeError("G11 start-of-world city unexpectedly has a market building")

        outbound = market.send_resources(
            db,
            city,
            schemas.TransportRequest(target_city_id=target.id, wood=100),
        )
        if market._get_available_merchants(db, city) != 400:
            raise RuntimeError("G11 outbound transport did not reserve start capacity")

        outbound.arrival_time = utc_now() - timedelta(seconds=1)
        db.add(outbound)
        db.commit()
        processed = movement.resolve_due_movements(db)
        if [item.id for item in processed] != [outbound.id]:
            raise RuntimeError(
                f"G11 outbound transport was not resolved exactly once: {[item.id for item in processed]}"
            )

        db.expire_all()
        target = db.query(models.City).filter_by(id=target.id).one()
        city = db.query(models.City).filter_by(id=city.id).one()
        if abs(float(target.wood) - 4950.0) > 0.1:
            raise RuntimeError(f"G11 rejected cargo mutated destination storage: {target.wood}")

        return_march = (
            db.query(models.Movement)
            .filter_by(
                target_city_id=city.id,
                movement_type="transport_return",
                status="ongoing",
            )
            .one_or_none()
        )
        if return_march is None:
            raise RuntimeError("G11 did not create merchant return")
        if return_march.resources != {"capacity": 100, "wood": 100}:
            raise RuntimeError(f"G11 rejected cargo was not conserved: {return_march.resources}")
        if market._get_available_merchants(db, city) != 400:
            raise RuntimeError("G11 merchant capacity was released before return")

        return_march.arrival_time = utc_now() - timedelta(seconds=1)
        db.add(return_march)
        db.commit()
        processed_return = movement.resolve_due_movements(db)
        if [item.id for item in processed_return] != [return_march.id]:
            raise RuntimeError(
                f"G11 merchant return was not resolved exactly once: {[item.id for item in processed_return]}"
            )

        db.expire_all()
        city = db.query(models.City).filter_by(id=city.id).one()
        return_march = db.query(models.Movement).filter_by(id=return_march.id).one()
        if return_march.status != "completed":
            raise RuntimeError("G11 merchant return did not complete")
        if market._get_available_merchants(db, city) != balance.BASE_MERCHANT_CAPACITY:
            raise RuntimeError("G11 merchant capacity was not released on completed return")
        if float(city.wood) < 999.9:
            raise RuntimeError(f"G11 rejected wood was not returned to sender: {city.wood}")

        if movement.resolve_due_movements(db):
            raise RuntimeError("G11 retry unexpectedly processed another due movement")

        trade_reports = (
            db.query(models.Report)
            .filter_by(city_id=city.id, report_type="trade")
            .order_by(models.Report.id.asc())
            .all()
        )
        parsed = [json.loads(str(report.content)) for report in trade_reports]
        rejected = [payload for payload in parsed if payload.get("return_reason") == "insufficient_storage"]
        returned = [payload for payload in parsed if payload.get("type") == "transport_return"]
        if len(rejected) != 1 or len(returned) != 1:
            raise RuntimeError(f"G11 audit reports mismatch: {parsed}")

        print(
            "prepared-g11:"
            f"{user.id}:{world.id}:{city.id}:{target.id}:"
            f"rules={balance.COMMERCE_RULES_VERSION}:"
            f"outbound={outbound.id}:return={return_march.id}:"
            f"capacity={market._get_available_merchants(db, city)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

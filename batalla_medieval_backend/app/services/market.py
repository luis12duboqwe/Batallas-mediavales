import logging
from datetime import timedelta
from typing import Dict, List

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..utils import utc_now
from . import anticheat
from . import event as event_service
from . import movement as movement_service
from . import production

logger = logging.getLogger(__name__)

MARKET_BUILDING_NAME = "market"
MERCHANT_CAPACITY = 1000
TRANSPORT_BASE_SPEED = 1.0


def _get_market_capacity(city: models.City) -> int:
    market = next((b for b in city.buildings if b.name == MARKET_BUILDING_NAME), None)
    if not market:
        return 0
    return market.level * MERCHANT_CAPACITY


def _get_available_merchants(db: Session, city: models.City) -> int:
    total_capacity = _get_market_capacity(city)

    ongoing_transports = (
        db.query(models.Movement)
        .filter(
            models.Movement.origin_city_id == city.id,
            models.Movement.movement_type == "transport",
            models.Movement.status == "ongoing",
        )
        .all()
    )

    used_capacity = 0
    for move in ongoing_transports:
        res = move.resources or {}
        used_capacity += sum(res.values())

    returning_transports = (
        db.query(models.Movement)
        .filter(
            models.Movement.target_city_id == city.id,
            models.Movement.movement_type == "transport_return",
            models.Movement.status == "ongoing",
        )
        .all()
    )
    for move in returning_transports:
        res = move.resources or {}
        used_capacity += res.get("capacity", 0)

    active_offers = (
        db.query(models.MarketOffer)
        .filter(models.MarketOffer.city_id == city.id)
        .all()
    )
    for offer in active_offers:
        used_capacity += offer.offer_amount

    return max(0, total_capacity - used_capacity)


def _normalize_transport_resources(resources: Dict[str, int]) -> Dict[str, int]:
    normalized: Dict[str, int] = {}
    for resource, raw_amount in resources.items():
        if resource not in production.RESOURCE_FIELDS:
            raise HTTPException(status_code=400, detail=f"Invalid resource type: {resource}")
        amount = int(raw_amount)
        if amount < 0:
            raise HTTPException(status_code=400, detail="Resource amounts cannot be negative")
        if amount > 0:
            normalized[resource] = amount
    if not normalized:
        raise HTTPException(status_code=400, detail="Transport requires resources")
    return normalized


def _create_transport_uncommitted(
    db: Session,
    *,
    origin_city: models.City,
    target_city: models.City,
    resources: Dict[str, int],
) -> models.Movement:
    """Create a market transport without charging resources or committing.

    The caller must already hold the relevant city locks and reserve the
    resources. Keeping this helper commit-free lets an offer exchange persist
    both directions, the payment and offer consumption in one transaction.
    """

    normalized = _normalize_transport_resources(resources)
    if origin_city.world_id != target_city.world_id:
        raise HTTPException(status_code=400, detail="Target city is not in the same world")
    if origin_city.id == target_city.id:
        raise HTTPException(status_code=400, detail="Origin and target city must be different")

    modifiers = event_service.get_active_modifiers(db, world_id=origin_city.world_id)
    effective_speed = TRANSPORT_BASE_SPEED * modifiers.get("movement_speed", 1.0)
    world_speed = origin_city.world.speed_modifier if origin_city.world else 1.0
    speed = max(effective_speed * world_speed, 0.01)
    distance = movement_service.calculate_distance(origin_city, target_city)
    arrival_time = utc_now() + timedelta(hours=distance / speed)

    movement = models.Movement(
        origin_city_id=origin_city.id,
        target_city_id=target_city.id,
        movement_type="transport",
        troops={},
        resources=normalized,
        spy_count=0,
        arrival_time=arrival_time,
        speed_used=speed,
        world_id=origin_city.world_id,
        status="ongoing",
    )
    db.add(movement)
    db.flush()
    return movement


def _audit_transport_after_commit(
    db: Session,
    *,
    movement: models.Movement,
    origin_city: models.City,
    target_city: models.City,
) -> None:
    """Run monitoring after the economic transaction is already durable."""

    if not origin_city.owner:
        return
    try:
        anticheat.check_action_speed(db, origin_city.owner, "market_transport")
        anticheat.check_movement_legitimacy(
            db,
            origin_city,
            target_city,
            "transport",
            movement.arrival_time,
            movement.speed_used or TRANSPORT_BASE_SPEED,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to record market transport anti-cheat telemetry",
            extra={"movement_id": movement.id},
        )


def create_offer(
    db: Session, city: models.City, offer: schemas.MarketOfferCreate
) -> models.MarketOffer:
    """Reserve resources for a market offer under the city row lock."""

    city, production_gains = production.lock_and_recalculate_resources(db, city)
    db.expire(city, ["buildings"])

    if getattr(city, offer.offer_type) < offer.offer_amount:
        db.rollback()
        raise HTTPException(status_code=400, detail="Insufficient resources")

    available_capacity = _get_available_merchants(db, city)
    if available_capacity < offer.offer_amount:
        db.rollback()
        raise HTTPException(status_code=400, detail="Not enough merchant capacity")

    setattr(
        city,
        offer.offer_type,
        getattr(city, offer.offer_type) - offer.offer_amount,
    )

    db_offer = models.MarketOffer(
        city_id=city.id,
        world_id=city.world_id,
        offer_type=offer.offer_type,
        offer_amount=offer.offer_amount,
        request_type=offer.request_type,
        request_amount=offer.request_amount,
        is_alliance_only=offer.is_alliance_only,
    )
    db.add(db_offer)
    db.commit()
    db.refresh(db_offer)
    production.record_resource_gains(db, city, production_gains)
    return db_offer


def npc_trade(
    db: Session,
    city: models.City,
    offer_type: str,
    request_type: str,
    amount: int,
):
    """Instant 1:1 trade with NPC, serialized per city."""

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if offer_type == request_type:
        raise HTTPException(status_code=400, detail="Resources must be different")
    if offer_type not in production.RESOURCE_FIELDS or request_type not in production.RESOURCE_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid resource type")

    city, production_gains = production.lock_and_recalculate_resources(db, city)

    if getattr(city, offer_type) < amount:
        db.rollback()
        raise HTTPException(status_code=400, detail="Insufficient resources")

    setattr(city, offer_type, getattr(city, offer_type) - amount)
    storage_limit = production.get_storage_limit(city)
    requested_balance = getattr(city, request_type) + amount
    if requested_balance > storage_limit:
        db.rollback()
        raise HTTPException(status_code=400, detail="Not enough storage capacity")
    setattr(city, request_type, requested_balance)

    db.commit()
    db.refresh(city)
    production.record_resource_gains(db, city, production_gains)
    return city


def get_offers(
    db: Session,
    world_id: int,
    user_id: int = None,
    filter_alliance: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> List[models.MarketOffer]:
    query = (
        db.query(models.MarketOffer)
        .join(models.City)
        .filter(models.MarketOffer.world_id == world_id)
    )

    if user_id:
        user_alliance = (
            db.query(models.AllianceMember)
            .join(models.Alliance)
            .filter(
                models.AllianceMember.user_id == user_id,
                models.Alliance.world_id == world_id,
            )
            .first()
        )

        if user_alliance:
            alliance_id = user_alliance.alliance_id

            if filter_alliance:
                query = (
                    query.join(models.User, models.City.owner_id == models.User.id)
                    .join(
                        models.AllianceMember,
                        models.User.id == models.AllianceMember.user_id,
                    )
                    .filter(models.AllianceMember.alliance_id == alliance_id)
                )
            else:
                query = query.join(
                    models.User, models.City.owner_id == models.User.id
                ).outerjoin(
                    models.AllianceMember,
                    models.User.id == models.AllianceMember.user_id,
                )

                query = query.filter(
                    or_(
                        models.MarketOffer.is_alliance_only == False,  # noqa: E712
                        models.AllianceMember.alliance_id == alliance_id,
                    )
                )
        else:
            query = query.filter(models.MarketOffer.is_alliance_only == False)  # noqa: E712
    else:
        query = query.filter(models.MarketOffer.is_alliance_only == False)  # noqa: E712

    return query.offset(skip).limit(limit).all()


def accept_offer(db: Session, buyer_city: models.City, offer_id: int):
    """Atomically consume one offer and create both resource transports."""

    production_gains: Dict[str, float] = {}
    try:
        offer = (
            db.query(models.MarketOffer)
            .filter(
                models.MarketOffer.id == offer_id,
                models.MarketOffer.world_id == buyer_city.world_id,
            )
            .with_for_update()
            .one_or_none()
        )
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")

        seller_city_id = offer.city_id
        locked_cities = (
            db.query(models.City)
            .filter(models.City.id.in_([seller_city_id, buyer_city.id]))
            .order_by(models.City.id.asc())
            .with_for_update()
            .populate_existing()
            .all()
        )
        by_id = {city.id: city for city in locked_cities}
        seller_city = by_id.get(seller_city_id)
        locked_buyer = by_id.get(buyer_city.id)
        if seller_city is None or locked_buyer is None:
            raise HTTPException(status_code=404, detail="Market city not found")
        if seller_city.world_id != locked_buyer.world_id:
            raise HTTPException(status_code=400, detail="Offer is not in the same world")
        if seller_city.owner_id == locked_buyer.owner_id:
            raise HTTPException(status_code=400, detail="Cannot accept your own offer")

        locked_buyer, production_gains = production.recalculate_resources(
            db,
            locked_buyer,
            return_gains=True,
            commit=False,
        )
        db.expire(locked_buyer, ["buildings"])

        payment = {offer.request_type: offer.request_amount}
        if not production.check_cost(locked_buyer, payment):
            raise HTTPException(status_code=400, detail="Insufficient resources to pay")

        available_capacity = _get_available_merchants(db, locked_buyer)
        if available_capacity < offer.request_amount:
            raise HTTPException(status_code=400, detail="Not enough merchant capacity")

        # Seller resources were reserved exactly once by create_offer(). Buyer
        # payment is reserved exactly once here. The transport helper never pays.
        production.pay_cost(locked_buyer, payment)

        seller_resources = {offer.offer_type: offer.offer_amount}
        buyer_resources = payment.copy()
        db.delete(offer)
        db.flush()

        seller_movement = _create_transport_uncommitted(
            db,
            origin_city=seller_city,
            target_city=locked_buyer,
            resources=seller_resources,
        )
        buyer_movement = _create_transport_uncommitted(
            db,
            origin_city=locked_buyer,
            target_city=seller_city,
            resources=buyer_resources,
        )

        db.commit()
        db.refresh(seller_movement)
        db.refresh(buyer_movement)
    except Exception:
        db.rollback()
        raise

    production.record_resource_gains(db, locked_buyer, production_gains)
    _audit_transport_after_commit(
        db,
        movement=seller_movement,
        origin_city=seller_city,
        target_city=locked_buyer,
    )
    _audit_transport_after_commit(
        db,
        movement=buyer_movement,
        origin_city=locked_buyer,
        target_city=seller_city,
    )
    return seller_movement, buyer_movement


def cancel_offer(db: Session, city: models.City, offer_id: int):
    """Cancel and refund an offer exactly once."""

    offer = (
        db.query(models.MarketOffer)
        .filter(
            models.MarketOffer.id == offer_id,
            models.MarketOffer.world_id == city.world_id,
        )
        .with_for_update()
        .first()
    )
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    if offer.city_id != city.id:
        db.rollback()
        raise HTTPException(status_code=403, detail="Not your offer")

    city, production_gains = production.lock_and_recalculate_resources(db, city)
    setattr(city, offer.offer_type, getattr(city, offer.offer_type) + offer.offer_amount)

    db.delete(offer)
    db.commit()
    production.record_resource_gains(db, city, production_gains)


def send_resources(
    db: Session, origin_city: models.City, request: schemas.TransportRequest
):
    """Reserve resources and create one transport in one transaction."""

    resources = {
        "wood": request.wood,
        "clay": request.clay,
        "iron": request.iron,
    }
    normalized = _normalize_transport_resources(resources)
    total_amount = sum(normalized.values())
    production_gains: Dict[str, float] = {}

    try:
        target_city = (
            db.query(models.City)
            .filter(models.City.id == request.target_city_id)
            .one_or_none()
        )
        if target_city is None:
            raise HTTPException(status_code=404, detail="Target city not found")
        if target_city.world_id != origin_city.world_id:
            raise HTTPException(status_code=400, detail="Target city is not in the same world")
        if target_city.id == origin_city.id:
            raise HTTPException(status_code=400, detail="Origin and target city must be different")

        locked_origin, production_gains = production.lock_and_recalculate_resources(
            db, origin_city
        )
        db.expire(locked_origin, ["buildings"])

        if not production.check_cost(locked_origin, normalized):
            raise HTTPException(status_code=400, detail="Insufficient resources")

        available_capacity = _get_available_merchants(db, locked_origin)
        if available_capacity < total_amount:
            raise HTTPException(status_code=400, detail="Not enough merchant capacity")

        # Pay exactly once while the origin row is locked. The movement creator
        # is deliberately non-economic and commit-free.
        production.pay_cost(locked_origin, normalized)
        movement = _create_transport_uncommitted(
            db,
            origin_city=locked_origin,
            target_city=target_city,
            resources=normalized,
        )
        db.commit()
        db.refresh(movement)
    except Exception:
        db.rollback()
        raise

    production.record_resource_gains(db, locked_origin, production_gains)
    _audit_transport_after_commit(
        db,
        movement=movement,
        origin_city=locked_origin,
        target_city=target_city,
    )
    return movement

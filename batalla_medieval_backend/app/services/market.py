from typing import List

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from . import movement as movement_service
from . import production

MARKET_BUILDING_NAME = "market"
MERCHANT_CAPACITY = 1000


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
                        models.MarketOffer.is_alliance_only == False,
                        models.AllianceMember.alliance_id == alliance_id,
                    )
                )
        else:
            query = query.filter(models.MarketOffer.is_alliance_only == False)
    else:
        query = query.filter(models.MarketOffer.is_alliance_only == False)

    return query.offset(skip).limit(limit).all()


def accept_offer(db: Session, buyer_city: models.City, offer_id: int):
    """Accept an offer once, preventing concurrent buyers from consuming it twice."""

    offer = (
        db.query(models.MarketOffer)
        .filter(models.MarketOffer.id == offer_id)
        .with_for_update()
        .first()
    )
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    if offer.city_id == buyer_city.id:
        db.rollback()
        raise HTTPException(status_code=400, detail="Cannot accept own offer")

    buyer_city, production_gains = production.lock_and_recalculate_resources(
        db, buyer_city
    )
    db.expire(buyer_city, ["buildings"])

    if getattr(buyer_city, offer.request_type) < offer.request_amount:
        db.rollback()
        raise HTTPException(status_code=400, detail="Insufficient resources to pay")

    available_capacity = _get_available_merchants(db, buyer_city)
    if available_capacity < offer.request_amount:
        db.rollback()
        raise HTTPException(status_code=400, detail="Not enough merchant capacity")

    setattr(
        buyer_city,
        offer.request_type,
        getattr(buyer_city, offer.request_type) - offer.request_amount,
    )

    # Delete/flush before movement helpers perform their own commits. This makes
    # a concurrent second acceptance observe the offer as consumed rather than
    # dispatching the seller's reserved resources twice. BM-0032 will further
    # consolidate market dispatch into a single transaction.
    seller_city = offer.city
    seller_city_id = offer.city_id
    offer_type = offer.offer_type
    offer_amount = offer.offer_amount
    request_type = offer.request_type
    request_amount = offer.request_amount
    db.delete(offer)
    db.flush()

    movement_service.send_movement(
        db,
        origin_city=seller_city,
        target_city_id=buyer_city.id,
        movement_type="transport",
        resources={offer_type: offer_amount},
    )

    movement_service.send_movement(
        db,
        origin_city=buyer_city,
        target_city_id=seller_city_id,
        movement_type="transport",
        resources={request_type: request_amount},
    )

    db.commit()
    production.record_resource_gains(db, buyer_city, production_gains)


def cancel_offer(db: Session, city: models.City, offer_id: int):
    """Cancel and refund an offer exactly once."""

    offer = (
        db.query(models.MarketOffer)
        .filter(models.MarketOffer.id == offer_id)
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
    """Reserve transport resources while holding the origin-city row lock."""

    total_amount = request.wood + request.clay + request.iron
    if total_amount <= 0:
        raise HTTPException(status_code=400, detail="Must send at least one resource")
    if request.wood < 0 or request.clay < 0 or request.iron < 0:
        raise HTTPException(status_code=400, detail="Resource amounts cannot be negative")

    origin_city, production_gains = production.lock_and_recalculate_resources(
        db, origin_city
    )
    db.expire(origin_city, ["buildings"])

    if (
        origin_city.wood < request.wood
        or origin_city.clay < request.clay
        or origin_city.iron < request.iron
    ):
        db.rollback()
        raise HTTPException(status_code=400, detail="Insufficient resources")

    available_capacity = _get_available_merchants(db, origin_city)
    if available_capacity < total_amount:
        db.rollback()
        raise HTTPException(status_code=400, detail="Not enough merchant capacity")

    origin_city.wood -= request.wood
    origin_city.clay -= request.clay
    origin_city.iron -= request.iron

    movement_service.send_movement(
        db,
        origin_city=origin_city,
        target_city_id=request.target_city_id,
        movement_type="transport",
        resources={
            "wood": request.wood,
            "clay": request.clay,
            "iron": request.iron,
        },
    )

    db.commit()
    production.record_resource_gains(db, origin_city, production_gains)

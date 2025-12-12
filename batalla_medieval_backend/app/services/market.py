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
    # Total capacity
    total_capacity = _get_market_capacity(city)
    
    # Used capacity by ongoing movements (transport)
    # We need to check outgoing transport movements
    ongoing_transports = (
        db.query(models.Movement)
        .filter(
            models.Movement.origin_city_id == city.id,
            models.Movement.movement_type == "transport",
            models.Movement.status == "ongoing"
        )
        .all()
    )
    
    used_capacity = 0
    for move in ongoing_transports:
        res = move.resources or {}
        used_capacity += sum(res.values())

    # Check returning merchants (they are incoming to us, but belong to us)
    # Wait, return movement has target_city_id = our city.
    returning_transports = (
        db.query(models.Movement)
        .filter(
            models.Movement.target_city_id == city.id,
            models.Movement.movement_type == "transport_return",
            models.Movement.status == "ongoing"
        )
        .all()
    )
    for move in returning_transports:
        res = move.resources or {}
        used_capacity += res.get("capacity", 0)
        
    # Also check active offers?
    # Usually offers reserve merchants.
    active_offers = (
        db.query(models.MarketOffer)
        .filter(models.MarketOffer.city_id == city.id)
        .all()
    )
    for offer in active_offers:
        used_capacity += offer.offer_amount
        
    return max(0, total_capacity - used_capacity)


def create_offer(db: Session, city: models.City, offer: schemas.MarketOfferCreate) -> models.MarketOffer:
    production.recalculate_resources(db, city)
    
    # Check resources
    if getattr(city, offer.offer_type) < offer.offer_amount:
        raise HTTPException(status_code=400, detail="Insufficient resources")
        
    # Check merchants
    available_capacity = _get_available_merchants(db, city)
    if available_capacity < offer.offer_amount:
        raise HTTPException(status_code=400, detail="Not enough merchant capacity")
        
    # Deduct resources
    setattr(city, offer.offer_type, getattr(city, offer.offer_type) - offer.offer_amount)
    
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
    return db_offer


def npc_trade(db: Session, city: models.City, offer_type: str, request_type: str, amount: int):
    """Instant 1:1 trade with NPC."""
    production.recalculate_resources(db, city)
    
    if getattr(city, offer_type) < amount:
        raise HTTPException(status_code=400, detail="Insufficient resources")
        
    # Check storage capacity for requested resource
    # Assuming storage capacity logic exists in production or city model
    # For now, just add it, assuming storage limits are handled elsewhere or ignored for NPC trade
    # But usually we should check.
    
    # Deduct offered resource
    setattr(city, offer_type, getattr(city, offer_type) - amount)
    
    # Add requested resource
    setattr(city, request_type, getattr(city, request_type) + amount)
    
    db.commit()
    db.refresh(city)
    return city


def get_offers(db: Session, world_id: int, user_id: int = None, filter_alliance: bool = False, skip: int = 0, limit: int = 100) -> List[models.MarketOffer]:
    query = db.query(models.MarketOffer).join(models.City).filter(models.MarketOffer.world_id == world_id)
    
    if user_id:
        user_alliance = (
            db.query(models.AllianceMember)
            .join(models.Alliance)
            .filter(models.AllianceMember.user_id == user_id, models.Alliance.world_id == world_id)
            .first()
        )
        
        if user_alliance:
            alliance_id = user_alliance.alliance_id
            
            if filter_alliance:
                # Show ONLY offers from my alliance
                query = query.join(models.User, models.City.owner_id == models.User.id)\
                             .join(models.AllianceMember, models.User.id == models.AllianceMember.user_id)\
                             .filter(models.AllianceMember.alliance_id == alliance_id)
            else:
                # Show Public + My Alliance
                # We want to include offers that are NOT alliance only OR are from my alliance
                # This requires a subquery or a complex join.
                # Simplified: Just return all and let frontend filter? No, security.
                # Let's use a subquery for alliance members.
                
                # Actually, let's just filter out "Alliance Only" offers that are NOT from my alliance.
                # But we can't easily check "from my alliance" without joining.
                
                # Join with AllianceMember to check owner's alliance
                query = query.join(models.User, models.City.owner_id == models.User.id)\
                             .outerjoin(models.AllianceMember, models.User.id == models.AllianceMember.user_id)
                
                query = query.filter(
                    or_(
                        models.MarketOffer.is_alliance_only == False,
                        models.AllianceMember.alliance_id == alliance_id
                    )
                )
        else:
            # User not in alliance, show only public
            query = query.filter(models.MarketOffer.is_alliance_only == False)
    else:
        query = query.filter(models.MarketOffer.is_alliance_only == False)

    return query.offset(skip).limit(limit).all()


def accept_offer(db: Session, buyer_city: models.City, offer_id: int):
    offer = db.query(models.MarketOffer).filter(models.MarketOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
        
    if offer.city_id == buyer_city.id:
        raise HTTPException(status_code=400, detail="Cannot accept own offer")
        
    production.recalculate_resources(db, buyer_city)
    
    # Check buyer resources
    if getattr(buyer_city, offer.request_type) < offer.request_amount:
        raise HTTPException(status_code=400, detail="Insufficient resources to pay")
        
    # Check buyer merchants
    available_capacity = _get_available_merchants(db, buyer_city)
    if available_capacity < offer.request_amount:
        raise HTTPException(status_code=400, detail="Not enough merchant capacity")
        
    # Deduct buyer resources
    setattr(buyer_city, offer.request_type, getattr(buyer_city, offer.request_type) - offer.request_amount)
    
    # Create movement: Seller -> Buyer (carrying offer)
    # Note: Seller resources were already deducted when offer was created.
    # We just need to create the movement.
    movement_service.send_movement(
        db,
        origin_city=offer.city,
        target_city_id=buyer_city.id,
        movement_type="transport",
        resources={offer.offer_type: offer.offer_amount}
    )
    
    # Create movement: Buyer -> Seller (carrying payment)
    movement_service.send_movement(
        db,
        origin_city=buyer_city,
        target_city_id=offer.city_id,
        movement_type="transport",
        resources={offer.request_type: offer.request_amount}
    )
    
    # Delete offer
    db.delete(offer)
    db.commit()


def cancel_offer(db: Session, city: models.City, offer_id: int):
    offer = db.query(models.MarketOffer).filter(models.MarketOffer.id == offer_id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
        
    if offer.city_id != city.id:
        raise HTTPException(status_code=403, detail="Not your offer")
        
    # Refund resources
    production.recalculate_resources(db, city)
    setattr(city, offer.offer_type, getattr(city, offer.offer_type) + offer.offer_amount)
    
    db.delete(offer)
    db.commit()


def send_resources(db: Session, origin_city: models.City, request: schemas.TransportRequest):
    production.recalculate_resources(db, origin_city)
    
    total_amount = request.wood + request.clay + request.iron
    if total_amount <= 0:
        raise HTTPException(status_code=400, detail="Must send at least one resource")
        
    # Check resources
    if origin_city.wood < request.wood or origin_city.clay < request.clay or origin_city.iron < request.iron:
        raise HTTPException(status_code=400, detail="Insufficient resources")
        
    # Check merchants
    available_capacity = _get_available_merchants(db, origin_city)
    if available_capacity < total_amount:
        raise HTTPException(status_code=400, detail="Not enough merchant capacity")
        
    # Deduct resources
    origin_city.wood -= request.wood
    origin_city.clay -= request.clay
    origin_city.iron -= request.iron
    
    # Create movement
    movement_service.send_movement(
        db,
        origin_city=origin_city,
        target_city_id=request.target_city_id,
        movement_type="transport",
        resources={"wood": request.wood, "clay": request.clay, "iron": request.iron}
    )
    
    db.commit()

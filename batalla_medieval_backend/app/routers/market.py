from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..database import get_db
from ..routers.auth import get_current_user
from ..routers.responses import error_response
from ..services import market

router = APIRouter()


def get_city_or_404(db: Session, city_id: int, user: models.User, world_id: int) -> models.City:
    city = (
        db.query(models.City)
        .options(selectinload(models.City.buildings))
        .filter(
            models.City.id == city_id,
            models.City.owner_id == user.id,
            models.City.world_id == world_id,
        )
        .first()
    )
    if not city:
        raise error_response(404, "city_not_found", "City not found or not owned by user")
    return city


@router.post("/offers", response_model=schemas.MarketOfferResponse)
def create_offer(
    payload: schemas.MarketOfferCreate,
    city_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = get_city_or_404(db, city_id, current_user, world_id)
    return market.create_offer(db, city, payload)


@router.get("/offers", response_model=List[schemas.MarketOfferResponse])
def get_offers(
    world_id: int,
    filter_alliance: bool = False,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    offers = market.get_offers(db, world_id, current_user.id, filter_alliance, skip, limit)
    return offers

@router.post("/npc_trade")
def npc_trade(
    city_id: int,
    offer_type: str,
    request_type: str,
    amount: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = get_city_or_404(db, city_id, current_user, world_id)
    market.npc_trade(db, city, offer_type, request_type, amount)
    return {"message": "Trade successful"}


@router.post("/offers/{offer_id}/accept")
def accept_offer(
    offer_id: int,
    city_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = get_city_or_404(db, city_id, current_user, world_id)
    market.accept_offer(db, city, offer_id)
    return {"status": "accepted"}


@router.delete("/offers/{offer_id}")
def cancel_offer(
    offer_id: int,
    city_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = get_city_or_404(db, city_id, current_user, world_id)
    market.cancel_offer(db, city, offer_id)
    return {"status": "cancelled"}


@router.post("/transport")
def send_resources(
    payload: schemas.TransportRequest,
    city_id: int,
    world_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    city = get_city_or_404(db, city_id, current_user, world_id)
    market.send_resources(db, city, payload)
    return {"status": "sent"}

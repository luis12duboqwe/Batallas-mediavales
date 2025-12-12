from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MarketOfferBase(BaseModel):
    offer_type: Literal["wood", "clay", "iron"]
    offer_amount: int = Field(..., gt=0)
    request_type: Literal["wood", "clay", "iron"]
    request_amount: int = Field(..., gt=0)
    is_alliance_only: bool = False


class MarketOfferCreate(MarketOfferBase):
    pass


class MarketOfferResponse(MarketOfferBase):
    id: int
    city_id: int
    world_id: int
    created_at: datetime
    city_name: str | None = None
    owner_name: str | None = None

    class Config:
        from_attributes = True


class TransportRequest(BaseModel):
    target_city_id: int
    wood: int = Field(0, ge=0)
    clay: int = Field(0, ge=0)
    iron: int = Field(0, ge=0)

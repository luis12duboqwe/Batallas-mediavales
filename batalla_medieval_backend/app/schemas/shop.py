from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ShopItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    type: str
    price_rubies: int
    rarity: str
    preview_url: Optional[str] = None


class UserItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item: ShopItemRead
    acquired_at: datetime


class PurchaseResponse(BaseModel):
    item: ShopItemRead
    acquired_at: datetime
    remaining_rubies: int

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ShopItemRead(BaseModel):
    id: int
    name: str
    description: str
    type: str
    price_rubies: int
    rarity: str
    preview_url: Optional[str] = None

    class Config:
        orm_mode = True


class UserItemRead(BaseModel):
    item: ShopItemRead
    acquired_at: datetime

    class Config:
        orm_mode = True


class PurchaseResponse(BaseModel):
    item: ShopItemRead
    acquired_at: datetime
    remaining_rubies: int


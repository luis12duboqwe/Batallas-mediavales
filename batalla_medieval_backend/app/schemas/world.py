from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class WorldWinner(BaseModel):
    id: int
    username: str

    class Config:
        orm_mode = True


class WorldBase(BaseModel):
    name: str
    speed_modifier: float = 1.0
    resource_modifier: float = 1.0
    map_size: int = 100
    special_rules: str = ""
    is_active: bool = True


class WorldCreate(WorldBase):
    pass


class WorldRead(WorldBase):
    id: int
    created_at: datetime
    ended_at: Optional[datetime] = None
    winner_id: Optional[int] = None
    winner_alliance_id: Optional[int] = None
    winner: Optional[WorldWinner] = None

    class Config:
        orm_mode = True


class PlayerWorldRead(BaseModel):
    id: int
    user_id: int
    world_id: int
    starting_city_id: Optional[int] = None
    joined_at: datetime

    class Config:
        orm_mode = True


class WorldSelect(BaseModel):
    world_id: int

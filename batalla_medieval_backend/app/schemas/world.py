from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WorldWinner(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


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
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    ended_at: Optional[datetime] = None
    winner_id: Optional[int] = None
    winner_alliance_id: Optional[int] = None
    winner: Optional[WorldWinner] = None


class PlayerWorldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    world_id: int
    starting_city_id: Optional[int] = None
    joined_at: datetime


class WorldSelect(BaseModel):
    world_id: int

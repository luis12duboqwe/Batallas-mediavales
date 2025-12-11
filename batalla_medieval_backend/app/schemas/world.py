from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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

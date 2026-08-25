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
    pve_rules_version: str = "2026.08.25-bm0067-v1"
    pve_last_tick_at: Optional[datetime] = None
    winner_id: Optional[int] = None
    winner_alliance_id: Optional[int] = None
    winner: Optional[WorldWinner] = None


class ActiveWorldSnapshot(BaseModel):
    """Persisted selector state plus the currently active world catalogue."""

    current_world_id: Optional[int] = None
    worlds: list[WorldRead]


class PlayerWorldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    world_id: int
    starting_city_id: Optional[int] = None
    joined_at: datetime


class WorldSelect(BaseModel):
    world_id: int

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


WorldLifecycleStatus = Literal["draft", "open", "paused", "closed", "archived"]


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
    map_size: int = Field(default=100, ge=10)
    # Administration may explicitly open a world at creation, but draft is safe.
    lifecycle_status: Literal["draft", "open"] = "draft"


class WorldRead(WorldBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lifecycle_status: WorldLifecycleStatus
    lifecycle_changed_at: datetime
    pause_started_at: Optional[datetime] = None
    created_at: datetime
    ended_at: Optional[datetime] = None
    winner_id: Optional[int] = None
    winner_alliance_id: Optional[int] = None
    winner: Optional[WorldWinner] = None


class WorldLifecycleTransition(BaseModel):
    target_status: WorldLifecycleStatus
    reason: str = Field(min_length=1, max_length=1000)


class ActiveWorldSnapshot(BaseModel):
    """Persisted selector state plus the currently open world catalogue."""

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

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel


class MovementBase(BaseModel):
    origin_city_id: int
    target_city_id: Optional[int] = None
    target_oasis_id: Optional[int] = None
    movement_type: str
    spy_count: int = 0
    troops: Dict[str, int] = {}
    resources: Dict[str, int] = {}
    world_id: int


class MovementCreate(MovementBase):
    arrival_time: datetime | None = None
    target_building: Optional[str] = None


class MovementRead(MovementBase):
    id: int
    arrival_time: datetime
    created_at: datetime
    status: str
    speed_used: float | None = None
    target_building: Optional[str] = None

    class Config:
        orm_mode = True

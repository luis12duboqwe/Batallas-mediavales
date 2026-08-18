from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AdventureBase(BaseModel):
    difficulty: str
    duration: int
    status: str


class AdventureRead(AdventureBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hero_id: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AdventureClaimResponse(BaseModel):
    status: str
    damage: int
    xp: int
    loot: Optional[dict] = None

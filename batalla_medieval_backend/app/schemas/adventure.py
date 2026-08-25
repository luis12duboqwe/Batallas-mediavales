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
    rules_version: Optional[str] = None
    outcome_seed: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AdventureClaimResponse(BaseModel):
    status: str
    damage: int
    xp: int
    loot: Optional[dict] = None
    rules_version: str
    seed: str

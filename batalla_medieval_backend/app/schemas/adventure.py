from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class AdventureBase(BaseModel):
    difficulty: str
    duration: int
    status: str

class AdventureRead(AdventureBase):
    id: int
    hero_id: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AdventureClaimResponse(BaseModel):
    status: str
    damage: int
    xp: int
    loot: Optional[dict] = None

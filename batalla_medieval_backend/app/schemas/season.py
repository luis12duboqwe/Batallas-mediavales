from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SeasonBase(BaseModel):
    season_id: str
    world_id: str
    name: str
    start_date: datetime
    end_date: Optional[datetime] = None
    is_active: bool

    class Config:
        orm_mode = True


class SeasonCreate(BaseModel):
    world_id: str
    name: str


class SeasonRead(SeasonBase):
    id: int


class SeasonResultRead(BaseModel):
    user_id: int
    alliance_id: Optional[int] = None
    rank: int
    points: int
    rewards: List[str]

    class Config:
        orm_mode = True


class SeasonInfo(BaseModel):
    active_season: Optional[SeasonRead]
    latest_results: List[SeasonResultRead] = []

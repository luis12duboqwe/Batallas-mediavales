from typing import Optional

from pydantic import BaseModel, ConfigDict


class HeroBase(BaseModel):
    pass


class HeroRead(HeroBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    city_id: Optional[int]
    name: str
    level: int
    xp: int
    next_level_xp: int
    health: float
    status: str
    attack_points: int
    defense_points: int
    production_points: int
    available_points: int


class HeroDistributePoints(BaseModel):
    attack: int = 0
    defense: int = 0
    production: int = 0

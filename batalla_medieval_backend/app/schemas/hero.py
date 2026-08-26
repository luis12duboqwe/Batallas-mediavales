from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class HeroBase(BaseModel):
    pass


class HeroRead(HeroBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    world_id: int
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
    rules_version: str


class HeroDistributePoints(BaseModel):
    attack: int = Field(default=0, ge=0)
    defense: int = Field(default=0, ge=0)
    production: int = Field(default=0, ge=0)

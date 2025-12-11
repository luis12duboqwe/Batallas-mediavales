from datetime import datetime
from typing import List

from pydantic import BaseModel

from .building import BuildingRead
from .troop import TroopRead


class CityBase(BaseModel):
    name: str
    x: int = 0
    y: int = 0
    world_id: int


class CityCreate(CityBase):
    pass


class CityRead(CityBase):
    id: int
    wood: float
    clay: float
    iron: float
    loyalty: float
    population_max: int
    last_production: datetime
    is_protected: bool = False
    buildings: List[BuildingRead] = []
    troops: List[TroopRead] = []

    class Config:
        orm_mode = True

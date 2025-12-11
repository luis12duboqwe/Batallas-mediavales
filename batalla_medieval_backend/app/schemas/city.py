from datetime import datetime
from typing import List

from pydantic import BaseModel

from .building import BuildingRead
from .troop import TroopRead


class CityBase(BaseModel):
    name: str
    x: int = 0
    y: int = 0


class CityCreate(CityBase):
    pass


class CityRead(CityBase):
    id: int
    wood: float
    clay: float
    iron: float
    loyalty: float
    last_production: datetime
    buildings: List[BuildingRead] = []
    troops: List[TroopRead] = []

    class Config:
        orm_mode = True

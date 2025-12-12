from datetime import datetime
from typing import List

from pydantic import BaseModel

from .building import BuildingRead
from .troop import TroopRead
from .queue import BuildingQueueRead, TroopQueueRead
from .oasis import OasisRead


class CityBase(BaseModel):
    name: str
    x: int | None = None
    y: int | None = None
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
    researched_units: List[str] = []
    buildings: List[BuildingRead] = []
    troops: List[TroopRead] = []
    oases: List[OasisRead] = []

    class Config:
        orm_mode = True


class CityResourceStatus(BaseModel):
    city_id: int
    wood: float
    clay: float
    iron: float
    loyalty: float
    storage_limit: float
    production_per_hour: dict
    last_production: datetime
    is_protected: bool = False
    building_queue: list[BuildingQueueRead] = []
    troop_queue: list[TroopQueueRead] = []
    oases: List[OasisRead] = []

    class Config:
        orm_mode = True

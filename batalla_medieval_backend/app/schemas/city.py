from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

from .building import BuildingRead
from .troop import TroopRead
from .queue import BuildingQueueRead, TroopQueueRead
from .oasis import OasisRead


SettlementType = Literal["city", "camp"]


class CityBase(BaseModel):
    name: str
    x: int | None = None
    y: int | None = None
    world_id: int


class CityCreate(CityBase):
    pass


class CityRead(CityBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    settlement_type: SettlementType = "city"
    wood: float
    stone: float
    iron: float
    gold: float
    loyalty: float
    population_max: int
    last_production: datetime
    is_protected: bool = False
    researched_units: List[str] = Field(default_factory=list)
    buildings: List[BuildingRead] = Field(default_factory=list)
    troops: List[TroopRead] = Field(default_factory=list)
    oases: List[OasisRead] = Field(default_factory=list)


class CityResourceStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    city_id: int
    settlement_type: SettlementType = "city"
    wood: float
    stone: float
    iron: float
    gold: float
    population: int
    population_max: int
    loyalty: float
    storage_limit: float
    production_per_hour: dict
    last_production: datetime
    is_protected: bool = False
    building_queue: list[BuildingQueueRead] = Field(default_factory=list)
    troop_queue: list[TroopQueueRead] = Field(default_factory=list)
    oases: List[OasisRead] = Field(default_factory=list)

from typing import Dict

from pydantic import BaseModel, ConfigDict


class TroopBase(BaseModel):
    unit_type: str


class TroopCreate(TroopBase):
    quantity: int


class TroopRead(TroopBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quantity: int


class ResearchRequest(BaseModel):
    city_id: int
    unit_type: str


class UnitAvailability(BaseModel):
    unit_type: str
    training_cost: Dict[str, float]
    training_time_seconds: int
    training_requirements: Dict[str, int]
    research_cost: Dict[str, float]
    research_time_seconds: int
    research_requirements: Dict[str, int]
    researched: bool
    research_queued: bool
    training_requirements_met: bool
    research_requirements_met: bool
    population_cost: int
    population_capacity: int
    population_available: int
    population_capacity_met: bool
    upkeep_per_hour: float
    can_train: bool
    can_research: bool

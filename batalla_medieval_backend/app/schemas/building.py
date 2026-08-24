from typing import Any

from pydantic import BaseModel, ConfigDict


class BuildingBase(BaseModel):
    name: str


class BuildingCreate(BuildingBase):
    level: int = 1


class BuildingRead(BuildingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: int


class BuildingAvailability(BaseModel):
    name: str
    display_name: str
    description: str
    level: int
    max_level: int
    is_max_level: bool
    can_upgrade: bool
    cost: dict
    requirements_met: bool
    requirements: dict
    build_time: int
    effect: dict[str, Any]

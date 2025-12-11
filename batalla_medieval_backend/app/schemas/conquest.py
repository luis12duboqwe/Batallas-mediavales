from typing import Dict

from pydantic import BaseModel, Field


class ConquestRequest(BaseModel):
    origin_city_id: int
    target_city_id: int
    troops: Dict[str, int] = Field(default_factory=dict)


class ConquestResult(BaseModel):
    victory: bool
    conquered: bool
    loyalty: float


class FoundCityRequest(BaseModel):
    origin_city_id: int
    name: str
    x: int
    y: int

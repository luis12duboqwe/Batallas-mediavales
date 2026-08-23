from typing import Dict, Literal

from pydantic import BaseModel, ConfigDict, Field


SettlementType = Literal["city", "camp"]


class FoundSettlementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_city_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=100)
    x: int
    y: int
    settlement_type: SettlementType


class ExpansionStatus(BaseModel):
    world_id: int
    expansion_points: int = Field(..., ge=0)
    city_count: int = Field(..., ge=0)
    camp_count: int = Field(..., ge=0)
    point_costs: Dict[str, int]
    camp_promotion_point_cost: int
    city_founding_cost: Dict[str, float]
    camp_founding_cost: Dict[str, float]
    camp_promotion_cost: Dict[str, float]
    points_per_completion: Dict[str, int]

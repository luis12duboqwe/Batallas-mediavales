from typing import Literal, Optional

from pydantic import BaseModel


class MapTile(BaseModel):
    x: int
    y: int
    type: str
    city_id: Optional[int] = None
    city_name: Optional[str] = None
    settlement_type: Optional[Literal["city", "camp"]] = None
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None
    alliance_name: Optional[str] = None
    points: Optional[int] = 0
    oasis_id: Optional[int] = None
    resource_type: Optional[str] = None
    bonus_percent: Optional[int] = None
    is_conquered: Optional[bool] = None
    pve_tier: Optional[int] = None
    pve_rules_version: Optional[str] = None


class MapResponse(BaseModel):
    tiles: list[MapTile]

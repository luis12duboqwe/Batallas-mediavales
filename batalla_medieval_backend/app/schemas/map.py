from typing import Optional
from pydantic import BaseModel

class MapTile(BaseModel):
    x: int
    y: int
    type: str
    city_id: Optional[int] = None
    city_name: Optional[str] = None
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None
    alliance_name: Optional[str] = None
    points: Optional[int] = 0
    oasis_id: Optional[int] = None
    resource_type: Optional[str] = None
    bonus_percent: Optional[int] = None
    is_conquered: Optional[bool] = None

class MapResponse(BaseModel):
    tiles: list[MapTile]

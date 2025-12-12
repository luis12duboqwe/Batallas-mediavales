from pydantic import BaseModel
from typing import Optional, Dict

class OasisBase(BaseModel):
    x: int
    y: int
    resource_type: str
    bonus_percent: int

class OasisRead(OasisBase):
    id: int
    world_id: int
    owner_city_id: Optional[int] = None
    troops: Dict[str, int] = {}

    class Config:
        orm_mode = True

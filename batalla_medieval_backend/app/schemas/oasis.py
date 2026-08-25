from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class OasisBase(BaseModel):
    x: int
    y: int
    resource_type: str
    bonus_percent: int


class OasisRead(OasisBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    world_id: int
    owner_city_id: Optional[int] = None
    troops: Dict[str, int] = Field(default_factory=dict)
    pve_tier: Optional[int] = None
    pve_rules_version: Optional[str] = None

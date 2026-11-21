from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

class WonderContributionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_city_id: int = Field(gt=0)
    source_city_id: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    wood: StrictInt = Field(default=0, ge=0)
    stone: StrictInt = Field(default=0, ge=0)
    iron: StrictInt = Field(default=0, ge=0)
    gold: StrictInt = Field(default=0, ge=0)

class WonderFundingRead(BaseModel):
    world_id: int
    city_id: int
    target_level: int
    rules_version: Literal["legacy-v1", "alliance-v2"]
    alliance_id: int | None
    status: str
    cost: dict[str, float]
    funded: dict[str, float]
    remaining: dict[str, float]
    can_queue: bool
    build_time: int

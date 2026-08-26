from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserBlockCreate(BaseModel):
    user_id: int = Field(gt=0)
    world_id: int = Field(gt=0)


class UserBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    blocker_id: int
    blocked_id: int
    world_id: int
    created_at: datetime

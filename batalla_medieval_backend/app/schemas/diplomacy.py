from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DiplomacyBase(BaseModel):
    alliance_target_id: int
    status: str  # "war", "nap", "ally"


class DiplomacyCreate(DiplomacyBase):
    pass


class DiplomacyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alliance_a_id: int
    alliance_b_id: int
    status: str
    created_at: datetime
    updated_at: datetime

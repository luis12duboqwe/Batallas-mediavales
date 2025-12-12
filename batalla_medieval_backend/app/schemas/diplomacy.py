from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class DiplomacyBase(BaseModel):
    alliance_target_id: int
    status: str # "war", "nap", "ally"

class DiplomacyCreate(DiplomacyBase):
    pass

class DiplomacyRead(BaseModel):
    id: int
    alliance_a_id: int
    alliance_b_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

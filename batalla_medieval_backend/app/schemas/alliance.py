from datetime import datetime
from typing import List

from pydantic import BaseModel


class AllianceBase(BaseModel):
    name: str
    description: str = ""


class AllianceCreate(AllianceBase):
    pass


class AllianceRead(AllianceBase):
    id: int
    leader_id: int
    created_at: datetime

    class Config:
        orm_mode = True


class AllianceMemberRead(BaseModel):
    id: int
    alliance_id: int
    user_id: int
    role: str

    class Config:
        orm_mode = True

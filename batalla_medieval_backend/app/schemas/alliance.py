from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


RANK_MEMBER = 1
RANK_GENERAL = 2
RANK_LEADER = 3


class AllianceBase(BaseModel):
    name: str
    description: str = ""


class AllianceCreate(AllianceBase):
    pass


class AllianceUpdate(BaseModel):
    description: Optional[str] = None
    diplomacy: Optional[str] = None


class AllianceRead(AllianceBase):
    id: int
    diplomacy: str
    leader_id: Optional[int]
    created_at: datetime

    class Config:
        orm_mode = True


class AllianceMemberRead(BaseModel):
    id: int
    alliance_id: int
    user_id: int
    rank: int

    class Config:
        orm_mode = True


class AllianceMemberPublic(BaseModel):
    user_id: int
    username: str
    rank: int


class AllianceInvitationCreate(BaseModel):
    user_id: int


class AllianceInvitationRead(BaseModel):
    id: int
    alliance_id: int
    invited_user_id: int
    invited_by_id: int
    status: str
    created_at: datetime
    responded_at: Optional[datetime]

    class Config:
        orm_mode = True


class AllianceChatMessageCreate(BaseModel):
    message: str


class AllianceChatMessageRead(BaseModel):
    id: int
    alliance_id: int
    user_id: int
    username: str
    message: str
    created_at: datetime

    class Config:
        orm_mode = True

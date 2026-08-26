from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


RANK_MEMBER = 1
RANK_GENERAL = 2
RANK_LEADER = 3

ALLIANCE_MASS_SUBJECT_MAX_LENGTH = 255
ALLIANCE_MASS_CONTENT_MAX_LENGTH = 10000


class AllianceBase(BaseModel):
    name: str
    description: str = ""
    world_id: int


class AllianceCreate(AllianceBase):
    pass


class AllianceUpdate(BaseModel):
    description: Optional[str] = None
    diplomacy: Optional[str] = None


class AllianceRead(AllianceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    diplomacy: str
    leader_id: Optional[int]
    created_at: datetime


class AllianceMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alliance_id: int
    user_id: int
    rank: int


class AllianceMemberPublic(BaseModel):
    id: int
    user_id: int
    username: str
    rank: int


class AllianceLeadershipTransfer(BaseModel):
    target_member_id: int = Field(gt=0)


class AllianceInvitationCreate(BaseModel):
    user_id: int


class AllianceInvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alliance_id: int
    invited_user_id: int
    invited_by_id: int
    status: str
    created_at: datetime
    responded_at: Optional[datetime]


class AllianceChatMessageCreate(BaseModel):
    message: str


class AllianceChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alliance_id: int
    user_id: int
    username: str
    message: str
    created_at: datetime


class AllianceMassMessage(BaseModel):
    subject: str = Field(min_length=1, max_length=ALLIANCE_MASS_SUBJECT_MAX_LENGTH)
    content: str = Field(min_length=1, max_length=ALLIANCE_MASS_CONTENT_MAX_LENGTH)

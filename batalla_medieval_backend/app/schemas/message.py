from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .user import UserPublic

MESSAGE_SUBJECT_MAX_LENGTH = 255
MESSAGE_CONTENT_MAX_LENGTH = 10000


class MessageBase(BaseModel):
    receiver_id: int = Field(gt=0)
    subject: str = Field(min_length=1, max_length=MESSAGE_SUBJECT_MAX_LENGTH)
    content: str = Field(min_length=1, max_length=MESSAGE_CONTENT_MAX_LENGTH)


class MessageCreate(MessageBase):
    pass


class MessageRead(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    world_id: Optional[int] = None
    read: bool
    timestamp: datetime
    sender: Optional[UserPublic]
    receiver: Optional[UserPublic]

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .user import UserPublic


class MessageBase(BaseModel):
    receiver_id: int
    subject: str
    content: str


class MessageCreate(MessageBase):
    pass


class MessageRead(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    read: bool
    timestamp: datetime
    sender: Optional[UserPublic]
    receiver: Optional[UserPublic]

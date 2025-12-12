from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from .user import UserPublic


class MessageBase(BaseModel):
    receiver_id: int
    subject: str
    content: str


class MessageCreate(MessageBase):
    pass


class MessageRead(MessageBase):
    id: int
    sender_id: int
    read: bool
    timestamp: datetime
    sender: Optional[UserPublic]
    receiver: Optional[UserPublic]

    class Config:
        orm_mode = True

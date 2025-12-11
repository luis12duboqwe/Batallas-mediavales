from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ChatMessageBase(BaseModel):
    content: str


class ChatMessageCreate(ChatMessageBase):
    channel: str
    receiver_id: Optional[int] = None
    world_id: Optional[int] = None
    alliance_id: Optional[int] = None


class ChatMessageRead(BaseModel):
    id: int
    user_id: int
    world_id: Optional[int]
    alliance_id: Optional[int]
    channel: str
    receiver_id: Optional[int]
    content: str
    timestamp: datetime

    class Config:
        orm_mode = True

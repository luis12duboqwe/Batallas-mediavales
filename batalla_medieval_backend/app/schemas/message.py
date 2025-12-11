from datetime import datetime

from pydantic import BaseModel


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

    class Config:
        orm_mode = True

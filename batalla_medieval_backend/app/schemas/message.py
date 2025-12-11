from datetime import datetime

from pydantic import BaseModel


class MessageBase(BaseModel):
    recipient_id: int
    content: str


class MessageCreate(MessageBase):
    pass


class MessageRead(MessageBase):
    id: int
    sender_id: int
    sent_at: datetime

    class Config:
        orm_mode = True

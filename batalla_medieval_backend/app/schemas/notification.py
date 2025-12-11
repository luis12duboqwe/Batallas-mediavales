from datetime import datetime

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: int
    title: str
    body: str
    type: str
    created_at: datetime
    read: bool

    class Config:
        orm_mode = True

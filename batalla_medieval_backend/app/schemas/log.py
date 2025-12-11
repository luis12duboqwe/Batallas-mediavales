from datetime import datetime

from pydantic import BaseModel


class LogBase(BaseModel):
    user_id: int
    action: str
    details: str
    timestamp: datetime


class LogCreate(BaseModel):
    user_id: int
    action: str
    details: str


class LogRead(LogBase):
    id: int

    class Config:
        orm_mode = True

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    model_config = ConfigDict(from_attributes=True)

    id: int

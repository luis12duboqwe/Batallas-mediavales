from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AdminBotLogBase(BaseModel):
    user_id: Optional[int] = None
    action: str
    details: str
    timestamp: datetime


class AdminBotLogRead(AdminBotLogBase):
    id: int

    class Config:
        orm_mode = True


class AdminBotRunResponse(BaseModel):
    detail: str
    actions: list[str]

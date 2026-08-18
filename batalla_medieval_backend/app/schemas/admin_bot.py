from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AdminBotLogBase(BaseModel):
    user_id: Optional[int] = None
    action: str
    details: str
    timestamp: datetime


class AdminBotLogRead(AdminBotLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class AdminBotRunResponse(BaseModel):
    detail: str
    actions: list[str]

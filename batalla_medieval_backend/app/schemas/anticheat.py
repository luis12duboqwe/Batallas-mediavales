from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AntiCheatFlagBase(BaseModel):
    user_id: int
    type_of_violation: str
    severity: str
    details: str
    reviewed_by_admin: bool = False
    resolved_status: str
    reviewer_id: Optional[int] = None


class AntiCheatFlagRead(AntiCheatFlagBase):
    id: int
    timestamp: datetime

    class Config:
        orm_mode = True


class AntiCheatResolveRequest(BaseModel):
    resolved_status: str = "resolved"
    reviewed_by_admin: bool = True

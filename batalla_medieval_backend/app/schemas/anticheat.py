from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AntiCheatFlagBase(BaseModel):
    user_id: int
    type_of_violation: str
    severity: str
    details: str
    reviewed_by_admin: bool = False
    resolved_status: str
    reviewer_id: Optional[int] = None


class AntiCheatFlagRead(AntiCheatFlagBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime


class AntiCheatResolveRequest(BaseModel):
    resolved_status: str = "resolved"
    reviewed_by_admin: bool = True

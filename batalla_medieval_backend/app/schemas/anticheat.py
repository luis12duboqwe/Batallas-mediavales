from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


AntiCheatResolutionStatus = Literal[
    "resolved",
    "confirmed",
    "false_positive",
    "monitoring",
    "dismissed",
]


class AntiCheatFlagBase(BaseModel):
    user_id: int
    type_of_violation: str
    severity: str
    details: str
    reviewed_by_admin: bool = False
    resolved_status: str
    reviewer_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    resolution_reason: Optional[str] = None


class AntiCheatFlagRead(AntiCheatFlagBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime


class AntiCheatResolveRequest(BaseModel):
    resolved_status: AntiCheatResolutionStatus = "resolved"
    # Compatibility-only input. The server is authoritative and always records
    # a successful review as reviewed regardless of this client value.
    reviewed_by_admin: Optional[bool] = None

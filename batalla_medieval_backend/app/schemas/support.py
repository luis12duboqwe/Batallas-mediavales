from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


SupportStatus = Literal["open", "in_progress", "resolved", "closed"]
SupportPriority = Literal["low", "normal", "high", "urgent"]


class SupportCaseCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=5, max_length=5000)
    world_id: Optional[int] = None

    @field_validator("subject", "description", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class SupportCaseAdminUpdate(BaseModel):
    status: Optional[SupportStatus] = None
    priority: Optional[SupportPriority] = None
    assigned_to_id: Optional[int] = None
    resolution: Optional[str] = Field(default=None, max_length=5000)
    reason: str = Field(min_length=1, max_length=1000)


class SupportCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requester_id: int
    world_id: Optional[int] = None
    assigned_to_id: Optional[int] = None
    subject: str
    description: str
    status: SupportStatus
    priority: SupportPriority
    resolution: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

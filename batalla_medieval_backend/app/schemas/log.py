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
    target_type: str | None = None
    target_id: int | None = None
    reason: str | None = None
    before_state: str | None = None
    after_state: str | None = None
    reversible: bool = False
    reversed_at: datetime | None = None
    reversed_by_id: int | None = None
    support_case_id: int | None = None

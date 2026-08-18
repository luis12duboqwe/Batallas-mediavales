from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SpyReportBase(BaseModel):
    city_id: int
    attacker_city_id: int | None
    defender_city_id: int
    success: bool
    reported_as_unknown: bool
    content: str


class SpyReportCreate(SpyReportBase):
    pass


class SpyReportRead(SpyReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

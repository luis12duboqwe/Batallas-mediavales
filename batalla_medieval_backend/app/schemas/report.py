from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReportBase(BaseModel):
    city_id: int
    world_id: int
    report_type: str
    content: str
    attacker_city_id: int | None = None
    defender_city_id: int | None = None


class ReportCreate(ReportBase):
    pass


class ReportRead(ReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

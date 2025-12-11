from datetime import datetime

from pydantic import BaseModel


class ReportBase(BaseModel):
    city_id: int
    report_type: str
    content: str


class ReportCreate(ReportBase):
    pass


class ReportRead(ReportBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True

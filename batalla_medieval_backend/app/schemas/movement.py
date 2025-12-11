from datetime import datetime

from pydantic import BaseModel


class MovementBase(BaseModel):
    origin_city_id: int
    target_city_id: int
    movement_type: str
    troops_payload: dict[str, int]


class MovementCreate(MovementBase):
    arrival_time: datetime


class MovementRead(MovementBase):
    id: int
    arrival_time: datetime
    status: str

    class Config:
        orm_mode = True

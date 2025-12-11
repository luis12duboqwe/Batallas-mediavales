from datetime import datetime

from pydantic import BaseModel

from .movement import MovementRead


class BuildingQueueBase(BaseModel):
    city_id: int
    building_type: str


class BuildingQueueCreate(BuildingQueueBase):
    pass


class BuildingQueueRead(BuildingQueueBase):
    id: int
    target_level: int
    finish_time: datetime

    class Config:
        orm_mode = True


class TroopQueueBase(BaseModel):
    city_id: int
    troop_type: str
    amount: int


class TroopQueueCreate(TroopQueueBase):
    pass


class TroopQueueRead(TroopQueueBase):
    id: int
    finish_time: datetime

    class Config:
        orm_mode = True


class QueueStatus(BaseModel):
    building_queues: list[BuildingQueueRead]
    troop_queues: list[TroopQueueRead]
    movements: list[MovementRead]

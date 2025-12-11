from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EventModifiers(BaseModel):
    production_speed: float = 1.0
    troop_training_speed: float = 1.0
    movement_speed: float = 1.0
    spy_modifier: float = 1.0
    loot_modifier: float = 1.0


class EventBase(BaseModel):
    world_id: int = 1
    name: str
    description: str
    start_time: datetime
    end_time: datetime
    modifiers: EventModifiers = Field(default_factory=EventModifiers)


class EventCreate(BaseModel):
    world_id: int = 1
    event_type: str
    start_time: datetime
    end_time: datetime


class EventRead(EventBase):
    id: int

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class ActiveEventResponse(BaseModel):
    event: Optional[EventRead]
    modifiers: EventModifiers

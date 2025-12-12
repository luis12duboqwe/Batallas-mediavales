from datetime import datetime
from typing import Dict, Any

from sqlalchemy import JSON, Column, DateTime, Integer, String

from ..database import Base
from ..utils import get_utc_now


class WorldEvent(Base):
    __tablename__ = "world_events"

    id = Column(Integer, primary_key=True, index=True)
    world_id = Column(Integer, nullable=False, index=True, default=1)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    start_time = Column(DateTime, default=get_utc_now, nullable=False)
    end_time = Column(DateTime, nullable=False)
    modifiers = Column(
        JSON,
        default=lambda: {
            "production_speed": 1.0,
            "troop_training_speed": 1.0,
            "movement_speed": 1.0,
            "spy_modifier": 1.0,
            "loot_modifier": 1.0,
        },
        nullable=False,
    )

    def get_modifiers(self) -> Dict[str, Any]:
        return self.modifiers or {}

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class Movement(Base):
    __tablename__ = "movements"

    id = Column(Integer, primary_key=True, index=True)
    origin_city_id = Column(Integer, ForeignKey("cities.id"))
    target_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    target_oasis_id = Column(Integer, ForeignKey("oases.id"), nullable=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False)
    movement_type = Column(String, nullable=False)  # attack, spy, reinforce, return, transport
    troops = Column(JSON, default={})
    resources = Column(JSON, default={})  # wood, clay, iron
    spy_count = Column(Integer, default=0)
    arrival_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    speed_used = Column(Float, nullable=True)
    status = Column(String, default="ongoing")
    target_building = Column(String, nullable=True) # For catapult attacks

    origin_city = relationship("City", back_populates="origin_movements", foreign_keys=[origin_city_id])
    target_city = relationship("City", back_populates="target_movements", foreign_keys=[target_city_id])
    target_oasis = relationship("Oasis")
    world = relationship("World", back_populates="movements")

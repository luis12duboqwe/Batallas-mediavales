from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class Movement(Base):
    __tablename__ = "movements"

    id = Column(Integer, primary_key=True, index=True)
    origin_city_id = Column(Integer, ForeignKey("cities.id"))
    target_city_id = Column(Integer, ForeignKey("cities.id"))
    movement_type = Column(String, nullable=False)  # attack, spy, reinforce, return
    spy_count = Column(Integer, default=0)
    arrival_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    speed_used = Column(Float, nullable=True)
    status = Column(String, default="ongoing")

    origin_city = relationship("City", back_populates="origin_movements", foreign_keys=[origin_city_id])
    target_city = relationship("City", back_populates="target_movements", foreign_keys=[target_city_id])

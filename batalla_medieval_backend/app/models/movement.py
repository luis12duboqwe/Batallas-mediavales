from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class Movement(Base):
    __tablename__ = "movements"

    id = Column(Integer, primary_key=True, index=True)
    origin_city_id = Column(Integer, ForeignKey("cities.id"))
    target_city_id = Column(Integer, ForeignKey("cities.id"))
    movement_type = Column(String, nullable=False)  # attack, spy, reinforce, return
    arrival_time = Column(DateTime, nullable=False)
    status = Column(String, default="ongoing")

    origin_city = relationship("City", back_populates="origin_movements", foreign_keys=[origin_city_id])
    target_city = relationship("City", back_populates="target_movements", foreign_keys=[target_city_id])

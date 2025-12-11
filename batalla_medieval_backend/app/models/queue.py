from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class BuildingQueue(Base):
    __tablename__ = "building_queue"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True)
    building_type = Column(String, nullable=False)
    target_level = Column(Integer, nullable=False)
    finish_time = Column(DateTime, nullable=False)

    city = relationship("City", back_populates="building_queue")


class TroopQueue(Base):
    __tablename__ = "troop_queue"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True)
    troop_type = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    finish_time = Column(DateTime, nullable=False)

    city = relationship("City", back_populates="troop_queue")

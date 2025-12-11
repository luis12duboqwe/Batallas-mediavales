from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"))
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)
    wood = Column(Float, default=500.0)
    clay = Column(Float, default=500.0)
    iron = Column(Float, default=500.0)
    loyalty = Column(Float, default=100.0)
    population_max = Column(Integer, default=100)
    last_production = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="cities")
    buildings = relationship("Building", back_populates="city", cascade="all, delete-orphan")
    troops = relationship("Troop", back_populates="city", cascade="all, delete-orphan")
    origin_movements = relationship("Movement", back_populates="origin_city", foreign_keys="Movement.origin_city_id")
    target_movements = relationship("Movement", back_populates="target_city", foreign_keys="Movement.target_city_id")
    building_queue = relationship(
        "BuildingQueue", back_populates="city", cascade="all, delete-orphan", uselist=True
    )
    troop_queue = relationship("TroopQueue", back_populates="city", cascade="all, delete-orphan", uselist=True)

from sqlalchemy import Column, ForeignKey, Integer, String, Float, JSON
from sqlalchemy.orm import relationship

from ..database import Base


class Oasis(Base):
    __tablename__ = "oases"

    id = Column(Integer, primary_key=True, index=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    
    # wood, clay, iron, crop
    resource_type = Column(String, nullable=False) 
    bonus_percent = Column(Integer, default=25)
    
    owner_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    
    # Troops guarding the oasis (barbarians/animals)
    troops = Column(JSON, default={}) 

    world = relationship("World")
    owner_city = relationship("City", back_populates="oases")

from sqlalchemy import Column, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import relationship

from ..database import Base


class Oasis(Base):
    __tablename__ = "oases"

    id = Column(Integer, primary_key=True, index=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)

    # Canonical BM-0060 resource key: wood, stone, iron or gold.
    resource_type = Column(String, nullable=False)
    bonus_percent = Column(Integer, default=25)

    owner_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)

    # Neutral guards use canonical unit keys from the BM-0063 unit catalog.
    troops = Column(JSON, default=dict)

    world = relationship("World")
    owner_city = relationship("City", back_populates="oases")

from sqlalchemy import Column, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class Building(Base):
    __tablename__ = "buildings"
    __table_args__ = (
        Index("ux_buildings_city_name", "city_id", "name", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True)
    name = Column(String, nullable=False)
    level = Column(Integer, default=1)

    city = relationship("City", back_populates="buildings")

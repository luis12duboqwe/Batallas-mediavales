from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class Troop(Base):
    __tablename__ = "troops"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True)
    unit_type = Column(String, nullable=False)
    quantity = Column(Integer, default=0)

    city = relationship("City", back_populates="troops")

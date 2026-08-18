from sqlalchemy import Column, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class Research(Base):
    __tablename__ = "research"
    __table_args__ = (
        Index("ux_research_city_tech", "city_id", "tech_name", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True)
    tech_name = Column(String, nullable=False)
    level = Column(Integer, default=1)

    city = relationship("City", back_populates="research")

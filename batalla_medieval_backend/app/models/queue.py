from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import relationship

from ..database import Base


class BuildingQueue(Base):
    __tablename__ = "building_queue"
    __table_args__ = (
        Index(
            "ux_building_queue_city_type",
            "city_id",
            "building_type",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True)
    building_type = Column(String, nullable=False)
    target_level = Column(Integer, nullable=False)
    finish_time = Column(DateTime, nullable=False)
    paid_cost = Column(JSON, nullable=True)

    city = relationship("City", back_populates="building_queue")


class TroopQueue(Base):
    __tablename__ = "troop_queue"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True)
    troop_type = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    finish_time = Column(DateTime, nullable=False)
    paid_cost = Column(JSON, nullable=True)

    city = relationship("City", back_populates="troop_queue")


class ResearchQueue(Base):
    __tablename__ = "research_queue"
    __table_args__ = (
        Index("ux_research_queue_city", "city_id", unique=True),
        Index("ux_research_queue_city_tech", "city_id", "tech_name", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), index=True, nullable=False)
    tech_name = Column(String, nullable=False)
    finish_time = Column(DateTime, nullable=False)
    paid_cost = Column(JSON, nullable=True)

    city = relationship("City", back_populates="research_queue")

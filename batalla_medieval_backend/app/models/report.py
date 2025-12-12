from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"))
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False)
    report_type = Column(String, nullable=False)  # battle or spy
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)
    attacker_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    defender_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)

    # Disambiguate the three city foreign keys - specify foreign_keys explicitly
    city = relationship(
        "City",
        foreign_keys="[Report.city_id]",
        back_populates="reports",
        primaryjoin="Report.city_id==City.id",
    )
    attacker_city = relationship(
        "City",
        foreign_keys="[Report.attacker_city_id]",
        back_populates="attacker_reports",
        primaryjoin="Report.attacker_city_id==City.id",
    )
    defender_city = relationship(
        "City",
        foreign_keys="[Report.defender_city_id]",
        back_populates="defender_reports",
        primaryjoin="Report.defender_city_id==City.id",
    )

    world = relationship("World", back_populates="reports")

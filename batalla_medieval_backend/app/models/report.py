from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"))
    report_type = Column(String, nullable=False)  # battle or spy
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    attacker_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    defender_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)

    city = relationship("City")

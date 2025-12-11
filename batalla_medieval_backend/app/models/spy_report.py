from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from ..database import Base


class SpyReport(Base):
    __tablename__ = "spy_reports"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"))
    attacker_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    defender_city_id = Column(Integer, ForeignKey("cities.id"))
    success = Column(Boolean, default=False)
    reported_as_unknown = Column(Boolean, default=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    city = relationship("City", foreign_keys=[city_id])
    attacker_city = relationship("City", foreign_keys=[attacker_city_id])
    defender_city = relationship("City", foreign_keys=[defender_city_id])

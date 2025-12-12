from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class Season(Base):
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(String, unique=True, index=True, nullable=False)
    world_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    start_date = Column(DateTime, default=get_utc_now, nullable=False)
    end_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    results = relationship("SeasonResult", back_populates="season", cascade="all, delete-orphan")

from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base
from ..utils import get_utc_now

class Adventure(Base):
    __tablename__ = "adventures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hero_id: Mapped[int] = mapped_column(Integer, ForeignKey("heroes.id"), nullable=False)
    
    difficulty: Mapped[str] = mapped_column(String, default="easy") # easy, medium, hard
    duration: Mapped[int] = mapped_column(Integer, default=300) # seconds
    
    status: Mapped[str] = mapped_column(String, default="available") # available, active, completed, expired
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    hero = relationship("Hero", backref="adventures")

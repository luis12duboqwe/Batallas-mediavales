from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..database import Base
from ..utils import get_utc_now


class Diplomacy(Base):
    __tablename__ = "diplomacy"
    __table_args__ = (UniqueConstraint("alliance_a_id", "alliance_b_id", name="uq_diplomacy_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alliance_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("alliances.id"), nullable=False)
    alliance_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("alliances.id"), nullable=False)
    
    # Status: "war", "nap", "ally", "pending_nap", "pending_ally"
    status: Mapped[str] = mapped_column(String, default="neutral")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    alliance_a = relationship("Alliance", foreign_keys=[alliance_a_id])
    alliance_b = relationship("Alliance", foreign_keys=[alliance_b_id])

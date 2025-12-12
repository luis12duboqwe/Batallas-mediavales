from datetime import datetime
from sqlalchemy import ForeignKey, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..database import Base
from ..utils import get_utc_now


class MarketOffer(Base):
    __tablename__ = "market_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    city_id: Mapped[int] = mapped_column(Integer, ForeignKey("cities.id"), nullable=False)
    world_id: Mapped[int] = mapped_column(Integer, ForeignKey("worlds.id"), nullable=False)
    
    # What I offer
    offer_type: Mapped[str] = mapped_column(String, nullable=False)  # wood, clay, iron
    offer_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # What I want
    request_type: Mapped[str] = mapped_column(String, nullable=False)  # wood, clay, iron
    request_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    
    is_alliance_only: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)
    
    city = relationship("City", back_populates="market_offers")
    world = relationship("World")

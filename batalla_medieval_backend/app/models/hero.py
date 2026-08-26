from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..utils import get_utc_now


class Hero(Base):
    __tablename__ = "heroes"
    __table_args__ = (
        UniqueConstraint("user_id", "world_id", name="uq_heroes_user_world"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    world_id: Mapped[int] = mapped_column(Integer, ForeignKey("worlds.id"), index=True, nullable=False)
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cities.id"), nullable=True)

    name: Mapped[str] = mapped_column(String, default="Comandante")
    level: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)

    health: Mapped[float] = mapped_column(Float, default=100.0)
    status: Mapped[str] = mapped_column(String, default="home")

    attack_points: Mapped[int] = mapped_column(Integer, default=0)
    defense_points: Mapped[int] = mapped_column(Integer, default=0)
    production_points: Mapped[int] = mapped_column(Integer, default=0)

    last_update: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)

    user = relationship("User", back_populates="heroes")
    world = relationship("World")
    city = relationship("City")
    items = relationship("HeroItem", back_populates="hero", cascade="all, delete-orphan")

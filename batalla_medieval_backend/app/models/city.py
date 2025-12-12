from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column

from ..database import Base
from ..utils import get_utc_now


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    world_id: Mapped[int] = mapped_column(Integer, ForeignKey("worlds.id"), index=True, nullable=False)
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    wood: Mapped[float] = mapped_column(Float, default=500.0)
    clay: Mapped[float] = mapped_column(Float, default=500.0)
    iron: Mapped[float] = mapped_column(Float, default=500.0)
    loyalty: Mapped[float] = mapped_column(Float, default=100.0)
    population_max: Mapped[int] = mapped_column(Integer, default=100)
    last_production: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)
    researched_units: Mapped[list] = mapped_column(JSON, default=["basic_infantry"])
    tile_type: Mapped[str] = mapped_column(String, default="grass")  # grass, forest, mountain, water

    owner = relationship("User", back_populates="cities")
    world = relationship("World", back_populates="cities")
    buildings = relationship("Building", back_populates="city", cascade="all, delete-orphan")
    troops = relationship("Troop", back_populates="city", cascade="all, delete-orphan")
    origin_movements = relationship("Movement", back_populates="origin_city", foreign_keys="Movement.origin_city_id")
    target_movements = relationship("Movement", back_populates="target_city", foreign_keys="Movement.target_city_id")
    building_queue = relationship(
        "BuildingQueue", back_populates="city", cascade="all, delete-orphan", uselist=True
    )
    troop_queue = relationship("TroopQueue", back_populates="city", cascade="all, delete-orphan", uselist=True)
    reports = relationship("Report", back_populates="city", foreign_keys="Report.city_id", cascade="all, delete-orphan")
    attacker_reports = relationship(
        "Report",
        back_populates="attacker_city",
        foreign_keys="Report.attacker_city_id",
        cascade="all, delete-orphan",
    )
    defender_reports = relationship(
        "Report",
        back_populates="defender_city",
        foreign_keys="Report.defender_city_id",
        cascade="all, delete-orphan",
    )
    market_offers = relationship("MarketOffer", back_populates="city", cascade="all, delete-orphan")
    oases = relationship("Oasis", back_populates="owner_city")
    research = relationship("Research", back_populates="city", cascade="all, delete-orphan")
    market_offers = relationship("MarketOffer", back_populates="city", cascade="all, delete-orphan")

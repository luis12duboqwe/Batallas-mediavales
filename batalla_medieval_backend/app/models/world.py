from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class World(Base):
    __tablename__ = "worlds"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    speed_modifier = Column(Float, default=1.0)
    resource_modifier = Column(Float, default=1.0)
    map_size = Column(Integer, default=100)
    special_rules = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    cities = relationship("City", back_populates="world", cascade="all, delete-orphan")
    users = relationship("User", back_populates="world")
    alliances = relationship("Alliance", back_populates="world", cascade="all, delete-orphan")
    movements = relationship("Movement", back_populates="world", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="world", cascade="all, delete-orphan")
    players = relationship("PlayerWorld", back_populates="world", cascade="all, delete-orphan")


class PlayerWorld(Base):
    __tablename__ = "player_world"
    __table_args__ = (UniqueConstraint("user_id", "world_id", name="uq_player_world_user_world"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False)
    starting_city_id = Column(Integer, ForeignKey("cities.id"), nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="world_memberships")
    world = relationship("World", back_populates="players")
    starting_city = relationship("City")

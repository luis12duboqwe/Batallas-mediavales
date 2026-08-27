from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class World(Base):
    __tablename__ = "worlds"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    speed_modifier = Column(Float, default=1.0)
    resource_modifier = Column(Float, default=1.0)
    map_size = Column(Integer, default=100)
    special_rules = Column(Text, default="")
    created_at = Column(DateTime, default=get_utc_now)
    # Legacy compatibility flag. BM-0072 makes lifecycle_status authoritative.
    is_active = Column(Boolean, default=True)
    lifecycle_status = Column(String(16), default="open", nullable=False, index=True)
    lifecycle_changed_at = Column(DateTime, default=get_utc_now, nullable=False)
    pause_started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    winner_id = Column(
        Integer,
        ForeignKey("users.id", name="fk_worlds_winner_id_users", use_alter=True),
        nullable=True,
    )
    winner_alliance_id = Column(
        Integer,
        ForeignKey(
            "alliances.id",
            name="fk_worlds_winner_alliance_id_alliances",
            use_alter=True,
        ),
        nullable=True,
    )

    cities = relationship("City", back_populates="world", cascade="all, delete-orphan")
    users = relationship("User", back_populates="world", foreign_keys="User.world_id")
    winner = relationship("User", foreign_keys=[winner_id])
    winner_alliance = relationship("Alliance", foreign_keys=[winner_alliance_id])
    alliances = relationship("Alliance", back_populates="world", cascade="all, delete-orphan", foreign_keys="Alliance.world_id")
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
    expansion_points = Column(Integer, default=0, nullable=False)
    joined_at = Column(DateTime, default=get_utc_now)

    user = relationship("User", back_populates="world_memberships")
    world = relationship("World", back_populates="players")
    starting_city = relationship("City")

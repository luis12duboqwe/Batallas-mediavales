from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class PremiumStatus(Base):
    __tablename__ = "premium_status"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    rubies_balance = Column(Integer, default=0)

    second_build_queue = Column(Boolean, default=False)
    second_troop_queue = Column(Boolean, default=False)
    rename_city_unlocked = Column(Boolean, default=False)
    rename_player_unlocked = Column(Boolean, default=False)
    extra_themes = Column(Boolean, default=False)
    profile_banner = Column(Boolean, default=False)
    instant_building_cancel = Column(Boolean, default=False)
    increased_message_storage = Column(Boolean, default=False)
    map_bookmarks = Column(Boolean, default=False)

    selected_theme = Column(String, nullable=True)
    selected_banner = Column(String, nullable=True)

    user = relationship("User", back_populates="premium_status")
    bookmarks = relationship(
        "MapBookmark", back_populates="owner", cascade="all, delete-orphan"
    )


class MapBookmark(Base):
    __tablename__ = "map_bookmarks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)

    owner = relationship("User", back_populates="bookmarks")

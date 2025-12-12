from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class Theme(Base):
    __tablename__ = "themes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    primary_color = Column(String, nullable=False)
    secondary_color = Column(String, nullable=False)
    background_url = Column(String, nullable=False)
    icon_pack_url = Column(String, nullable=False)
    locked = Column(Boolean, default=True)

    ownerships = relationship(
        "ThemeOwnership", back_populates="theme", cascade="all, delete-orphan"
    )


class ThemeOwnership(Base):
    __tablename__ = "user_themes"
    __table_args__ = (UniqueConstraint("user_id", "theme_id", name="uq_user_theme"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=False)
    source = Column(String, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)

    user = relationship("User", back_populates="theme_ownerships")
    theme = relationship("Theme", back_populates="ownerships")

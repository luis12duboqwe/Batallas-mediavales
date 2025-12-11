from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


class Alliance(Base):
    __tablename__ = "alliances"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, default="")
    leader_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("AllianceMember", back_populates="alliance", cascade="all, delete-orphan")


class AllianceMember(Base):
    __tablename__ = "alliance_members"

    id = Column(Integer, primary_key=True, index=True)
    alliance_id = Column(Integer, ForeignKey("alliances.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String, default="member")

    alliance = relationship("Alliance", back_populates="members")
    user = relationship("User", back_populates="alliances")

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class Alliance(Base):
    __tablename__ = "alliances"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    diplomacy = Column(String, default="neutral")
    leader_id = Column(Integer, ForeignKey("users.id"))
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False)
    created_at = Column(DateTime, default=get_utc_now)

    __table_args__ = (UniqueConstraint("name", "world_id", name="uq_alliance_name_world"),)

    members = relationship("AllianceMember", back_populates="alliance", cascade="all, delete-orphan")
    invitations = relationship("AllianceInvitation", back_populates="alliance", cascade="all, delete-orphan")
    chat_messages = relationship("AllianceChatMessage", back_populates="alliance", cascade="all, delete-orphan")
    world = relationship("World", back_populates="alliances", foreign_keys=[world_id])


class AllianceInvitation(Base):
    __tablename__ = "alliance_invitations"
    __table_args__ = (UniqueConstraint("alliance_id", "invited_user_id", name="uq_alliance_invite_user"),)

    id = Column(Integer, primary_key=True, index=True)
    alliance_id = Column(Integer, ForeignKey("alliances.id"), nullable=False)
    invited_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invited_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=get_utc_now)
    responded_at = Column(DateTime, nullable=True)

    alliance = relationship("Alliance", back_populates="invitations")
    invited_user = relationship(
        "User",
        foreign_keys=[invited_user_id],
        back_populates="alliance_invitations",
    )
    invited_by = relationship(
        "User",
        foreign_keys=[invited_by_id],
        back_populates="alliance_invitations_sent",
    )


class AllianceChatMessage(Base):
    __tablename__ = "alliance_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    alliance_id = Column(Integer, ForeignKey("alliances.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)

    alliance = relationship("Alliance", back_populates="chat_messages")
    user = relationship("User", back_populates="alliance_chat_messages")

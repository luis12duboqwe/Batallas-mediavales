from datetime import datetime
from typing import List

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    protection_ends_at = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, default=False)
    is_frozen = Column(Boolean, default=False)
    freeze_reason = Column(String, nullable=True)
    last_login_ip = Column(String, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_action_at = Column(DateTime, nullable=True)
    rename_tokens = Column(Integer, default=0)
    premium_theme_unlocked = Column(Boolean, default=False)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=True)

    cities = relationship("City", back_populates="owner", cascade="all, delete-orphan")
    premium_status = relationship(
        "PremiumStatus", back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    bookmarks = relationship("MapBookmark", back_populates="owner", cascade="all, delete-orphan")
    alliances = relationship("AllianceMember", back_populates="user", cascade="all, delete-orphan")
    alliance_invitations = relationship(
        "AllianceInvitation",
        back_populates="invited_user",
        foreign_keys="AllianceInvitation.invited_user_id",
        cascade="all, delete-orphan",
    )
    alliance_invitations_sent = relationship(
        "AllianceInvitation",
        foreign_keys="AllianceInvitation.invited_by_id",
        cascade="all, delete-orphan",
    )
    alliance_chat_messages = relationship(
        "AllianceChatMessage", back_populates="user", cascade="all, delete-orphan"
    )
    messages_sent = relationship(
        "Message", back_populates="sender", foreign_keys="Message.sender_id", cascade="all, delete-orphan"
    )
    messages_received = relationship(
        "Message", back_populates="receiver", foreign_keys="Message.receiver_id", cascade="all, delete-orphan"
    )
    logs = relationship("Log", back_populates="user", cascade="all, delete-orphan")
    quest_progress = relationship(
        "QuestProgress", back_populates="user", cascade="all, delete-orphan"
    )
    world = relationship("World", back_populates="users")
    world_memberships = relationship("PlayerWorld", back_populates="user", cascade="all, delete-orphan")

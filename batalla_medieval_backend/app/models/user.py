from datetime import datetime
from typing import List, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..utils import get_utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=get_utc_now)
    last_active_at: Mapped[datetime] = mapped_column(default=get_utc_now)
    protection_ends_at: Mapped[Optional[datetime]]
    is_admin: Mapped[bool] = mapped_column(default=False)
    rubies_balance: Mapped[int] = mapped_column(default=0)
    is_frozen: Mapped[bool] = mapped_column(default=False)
    email_notifications: Mapped[bool] = mapped_column(default=False)
    language: Mapped[str] = mapped_column(String, default="en")
    freeze_reason: Mapped[Optional[str]]
    last_login_ip: Mapped[Optional[str]]
    last_login_at: Mapped[Optional[datetime]]
    last_action_at: Mapped[Optional[datetime]]
    rename_tokens: Mapped[int] = mapped_column(default=0)
    tutorial_step: Mapped[int] = mapped_column(default=0)
    
    is_verified: Mapped[bool] = mapped_column(default=False)
    verification_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    premium_theme_unlocked: Mapped[bool] = mapped_column(default=False)
    world_id: Mapped[Optional[int]] = mapped_column(ForeignKey("worlds.id"))

    # Rankings
    attacker_points: Mapped[int] = mapped_column(default=0)
    defender_points: Mapped[int] = mapped_column(default=0)

    current_theme_id: Mapped[Optional[int]] = mapped_column(ForeignKey("themes.id"))

    hero: Mapped["Hero"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    cities: Mapped[List["City"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    premium_status: Mapped["PremiumStatus"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    bookmarks: Mapped[List["MapBookmark"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    alliances: Mapped[List["AllianceMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alliance_invitations: Mapped[List["AllianceInvitation"]] = relationship(
        "AllianceInvitation",
        back_populates="invited_user",
        foreign_keys="AllianceInvitation.invited_user_id",
        cascade="all, delete-orphan",
    )
    alliance_invitations_sent: Mapped[List["AllianceInvitation"]] = relationship(
        "AllianceInvitation",
        foreign_keys="AllianceInvitation.invited_by_id",
        cascade="all, delete-orphan",
    )
    alliance_chat_messages: Mapped[List["AllianceChatMessage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    messages_sent: Mapped[List["Message"]] = relationship(
        "Message", back_populates="sender", foreign_keys="Message.sender_id", cascade="all, delete-orphan"
    )
    messages_received: Mapped[List["Message"]] = relationship(
        "Message", back_populates="receiver", foreign_keys="Message.receiver_id", cascade="all, delete-orphan"
    )
    logs: Mapped[List["Log"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    achievement_progress: Mapped[List["AchievementProgress"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    theme_ownerships: Mapped[List["ThemeOwnership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    current_theme: Mapped["Theme"] = relationship("Theme", foreign_keys=[current_theme_id])
    items: Mapped[List["UserItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[List["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    quest_progress: Mapped[List["QuestProgress"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    world: Mapped["World"] = relationship(back_populates="users", foreign_keys=[world_id])
    world_memberships: Mapped[List["PlayerWorld"]] = relationship(back_populates="user", cascade="all, delete-orphan")

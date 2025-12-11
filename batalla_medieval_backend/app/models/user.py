from datetime import datetime
from typing import List

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    cities = relationship("City", back_populates="owner", cascade="all, delete-orphan")
    alliances = relationship("AllianceMember", back_populates="user", cascade="all, delete-orphan")
    messages_sent = relationship(
        "Message", back_populates="sender", foreign_keys="Message.sender_id", cascade="all, delete-orphan"
    )
    messages_received = relationship(
        "Message", back_populates="receiver", foreign_keys="Message.receiver_id", cascade="all, delete-orphan"
    )

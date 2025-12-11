from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=True)
    alliance_id = Column(Integer, ForeignKey("alliances.id"), nullable=True)
    channel = Column(String, nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
    world = relationship("World")
    alliance = relationship("Alliance")

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class QuestProgress(Base):
    __tablename__ = "quest_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quest_id = Column(Integer, ForeignKey("quests.id"), nullable=False, index=True)
    status = Column(String, default="pending")
    progress_data = Column(JSON, default={})

    __table_args__ = (UniqueConstraint("user_id", "quest_id", name="uq_user_quest"),)

    user = relationship("User", back_populates="quest_progress")
    quest = relationship("Quest", back_populates="progresses")

from sqlalchemy import Boolean, Column, Integer, JSON, String
from sqlalchemy.orm import relationship

from ..database import Base


class Quest(Base):
    __tablename__ = "quests"

    id = Column(Integer, primary_key=True, index=True)
    quest_id = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    requirements = Column(JSON, nullable=False, default={})
    reward = Column(JSON, nullable=False, default={})
    is_tutorial = Column(Boolean, default=False)

    progresses = relationship("QuestProgress", back_populates="quest", cascade="all, delete-orphan")

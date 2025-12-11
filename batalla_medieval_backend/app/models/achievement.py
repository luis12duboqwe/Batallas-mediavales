from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)
    requirement_type = Column(String, nullable=False)
    requirement_value = Column(Integer, nullable=False)
    reward_type = Column(String, nullable=False)
    reward_value = Column(String, nullable=False)

    progress = relationship(
        "AchievementProgress",
        back_populates="achievement",
        cascade="all, delete-orphan",
    )

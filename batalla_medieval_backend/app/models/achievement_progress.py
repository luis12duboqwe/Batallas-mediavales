from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class AchievementProgress(Base):
    __tablename__ = "achievement_progress"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    current_progress = Column(Integer, default=0)
    status = Column(String, default="pending")

    user = relationship("User", back_populates="achievement_progress")
    achievement = relationship("Achievement", back_populates="progress")

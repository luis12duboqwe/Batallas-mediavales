import json

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from ..database import Base


class SeasonResult(Base):
    __tablename__ = "season_results"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    alliance_id = Column(Integer, ForeignKey("alliances.id"), nullable=True)
    rank = Column(Integer, nullable=False)
    points = Column(Integer, default=0)
    rewards = Column(String, default="[]")

    season = relationship("Season", back_populates="results")
    user = relationship("User")
    alliance = relationship("Alliance")

    def set_rewards(self, rewards: list[str]) -> None:
        self.rewards = json.dumps(rewards)

    def get_rewards(self) -> list[str]:
        try:
            return json.loads(self.rewards)
        except json.JSONDecodeError:
            return []

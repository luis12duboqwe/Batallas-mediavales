from datetime import datetime
import json

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base


class AdminBotLog(Base):
    __tablename__ = "admin_bot_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=False, default="{}")
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")

    def set_details(self, data: dict) -> None:
        self.details = json.dumps(data)

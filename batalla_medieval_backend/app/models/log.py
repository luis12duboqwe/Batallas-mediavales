from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=False)
    target_type = Column(String(64), nullable=True, index=True)
    target_id = Column(Integer, nullable=True, index=True)
    reason = Column(Text, nullable=True)
    before_state = Column(Text, nullable=True)
    after_state = Column(Text, nullable=True)
    reversible = Column(Boolean, default=False, nullable=False)
    reversed_at = Column(DateTime, nullable=True)
    reversed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    support_case_id = Column(Integer, ForeignKey("support_cases.id"), nullable=True, index=True)
    timestamp = Column(DateTime, default=get_utc_now)

    user = relationship("User", back_populates="logs", foreign_keys=[user_id])
    reversed_by = relationship("User", foreign_keys=[reversed_by_id])

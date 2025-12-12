from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class AntiCheatFlag(Base):
    __tablename__ = "anti_cheat_flags"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type_of_violation = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    details = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=get_utc_now, nullable=False)
    reviewed_by_admin = Column(Boolean, default=False, nullable=False)
    resolved_status = Column(String, default="pending", nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])

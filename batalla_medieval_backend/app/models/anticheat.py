from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    reviewed_at = Column(DateTime, nullable=True)
    resolution_reason = Column(Text, nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])


class AntiCheatRateBucket(Base):
    __tablename__ = "anti_cheat_rate_buckets"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "action_key",
            name="uq_anticheat_rate_bucket_user_action",
        ),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_key = Column(String(96), nullable=False)
    window_started_at = Column(DateTime, default=get_utc_now, nullable=False)
    request_count = Column(Integer, default=0, nullable=False)
    blocked_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=get_utc_now, nullable=False)

    user = relationship("User", foreign_keys=[user_id])

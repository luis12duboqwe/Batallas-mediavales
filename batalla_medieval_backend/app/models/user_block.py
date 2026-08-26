from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class UserBlock(Base):
    __tablename__ = "user_blocks"
    __table_args__ = (
        UniqueConstraint(
            "blocker_id",
            "blocked_id",
            "world_id",
            name="uq_user_block_pair_world",
        ),
        Index("ix_user_blocks_blocker_world", "blocker_id", "world_id"),
        Index("ix_user_blocks_blocked_world", "blocked_id", "world_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    blocked_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    world_id = Column(Integer, ForeignKey("worlds.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)

    blocker = relationship("User", foreign_keys=[blocker_id])
    blocked = relationship("User", foreign_keys=[blocked_id])
    world = relationship("World")

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base


class AllianceMember(Base):
    __tablename__ = "alliance_members"
    __table_args__ = (UniqueConstraint("alliance_id", "user_id", name="uq_alliance_member_user"),)

    id = Column(Integer, primary_key=True, index=True)
    alliance_id = Column(Integer, ForeignKey("alliances.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rank = Column(Integer, default=1)

    alliance = relationship("Alliance", back_populates="members")
    user = relationship("User", back_populates="alliances")

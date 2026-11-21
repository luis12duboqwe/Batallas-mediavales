"""Escrow and idempotent contributions for versioned alliance wonders."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from ..database import Base
from ..utils import get_utc_now


class WonderFunding(Base):
    __tablename__ = "wonder_funding"
    __table_args__ = (
        UniqueConstraint(
            "city_id", "target_level", "owner_id", "alliance_id",
            name="uq_wonder_funding_project",
        ),
        CheckConstraint("target_level BETWEEN 1 AND 100", name="ck_wonder_funding_level"),
        CheckConstraint(
            "funded_wood >= 0 AND funded_stone >= 0 AND funded_iron >= 0 AND funded_gold >= 0",
            name="ck_wonder_funding_nonnegative",
        ),
    )

    id = Column(Integer, primary_key=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    alliance_id = Column(Integer, ForeignKey("alliances.id"), nullable=False)
    target_level = Column(Integer, nullable=False)
    funded_wood = Column(Integer, nullable=False, default=0)
    funded_stone = Column(Integer, nullable=False, default=0)
    funded_iron = Column(Integer, nullable=False, default=0)
    funded_gold = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="funding")
    created_at = Column(DateTime, nullable=False, default=get_utc_now)

    city = relationship("City")
    contributions = relationship("WonderContribution", back_populates="funding")


class WonderContribution(Base):
    __tablename__ = "wonder_contributions"
    __table_args__ = (
        UniqueConstraint("world_id", "contributor_id", "idempotency_key", name="uq_wonder_contrib_request"),
        CheckConstraint(
            "wood >= 0 AND stone >= 0 AND iron >= 0 AND gold >= 0 "
            "AND (wood + stone + iron + gold) > 0",
            name="ck_wonder_contrib_positive",
        ),
    )

    id = Column(Integer, primary_key=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False)
    funding_id = Column(Integer, ForeignKey("wonder_funding.id"), nullable=False)
    contributor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_city_id = Column(Integer, ForeignKey("cities.id"), nullable=False)
    idempotency_key = Column(String(80), nullable=False)
    wood = Column(Integer, nullable=False, default=0)
    stone = Column(Integer, nullable=False, default=0)
    iron = Column(Integer, nullable=False, default=0)
    gold = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=get_utc_now)
    funding = relationship("WonderFunding", back_populates="contributions")

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..utils import get_utc_now


class Adventure(Base):
    __tablename__ = "adventures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hero_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("heroes.id"), nullable=False, index=True
    )

    difficulty: Mapped[str] = mapped_column(String, default="easy")
    duration: Mapped[int] = mapped_column(Integer, default=300)
    status: Mapped[str] = mapped_column(String, default="available")
    rules_version: Mapped[str] = mapped_column(String, nullable=False)
    seed: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    hero = relationship("Hero", backref="adventures")

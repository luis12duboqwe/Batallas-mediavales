from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..utils import get_utc_now


class SupportCase(Base):
    __tablename__ = "support_cases"

    # BM-0090: protect active privacy requests against parallel POSTs even on
    # SQLite, where SELECT ... FOR UPDATE does not lock individual rows.
    # Ordinary support cases and resolved/closed history stay unrestricted.
    _privacy_active_predicate = text(
        "status IN ('open', 'in_progress') AND subject IN ("
        "'[PRIVACY] Solicitud de eliminación de cuenta', "
        "'[PRIVACY] Solicitud de corrección de datos', "
        "'[PRIVACY] Consulta sobre retención de datos', "
        "'[PRIVACY] Consulta sobre privacidad')"
    )
    __table_args__ = (
        Index(
            "uq_support_privacy_active_user_subject",
            "requester_id",
            "subject",
            unique=True,
            sqlite_where=_privacy_active_predicate,
            postgresql_where=_privacy_active_predicate,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    world_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("worlds.id"), nullable=True, index=True)
    assigned_to_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False, index=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=get_utc_now, onupdate=get_utc_now, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    requester = relationship("User", foreign_keys=[requester_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    world = relationship("World")

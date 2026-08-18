from datetime import datetime, timedelta, timezone

from ..config import get_settings
from ..models import User
from ..utils import utc_now

settings = get_settings()


def _as_utc(value: datetime) -> datetime:
    """Normalize persisted datetimes to timezone-aware UTC.

    SQLite commonly returns ``DateTime`` columns without tzinfo even when the
    application wrote an aware UTC value. PostgreSQL may preserve awareness.
    Domain code must handle both representations identically.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_protection_end(user: User) -> datetime | None:
    """Return the UTC-aware datetime when protection ends for a user."""

    if user.protection_ends_at:
        return _as_utc(user.protection_ends_at)
    if user.created_at:
        return _as_utc(user.created_at) + timedelta(hours=settings.protection_hours)
    return None


def get_protection_seconds_left(user: User) -> int:
    """Calculate remaining protection time in seconds."""

    protection_end = get_protection_end(user)
    if not protection_end:
        return 0
    remaining = (protection_end - _as_utc(utc_now())).total_seconds()
    return int(remaining) if remaining > 0 else 0


def is_user_protected(user: User) -> bool:
    """Check whether the user is still under protection."""

    return get_protection_seconds_left(user) > 0

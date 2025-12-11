from datetime import datetime, timedelta

from ..config import get_settings
from ..models import User

settings = get_settings()


def get_protection_end(user: User) -> datetime | None:
    """Return the datetime when protection ends for the given user."""
    if user.protection_ends_at:
        return user.protection_ends_at
    if user.created_at:
        return user.created_at + timedelta(hours=settings.protection_hours)
    return None


def get_protection_seconds_left(user: User) -> int:
    """Calculate remaining protection time in seconds."""
    protection_end = get_protection_end(user)
    if not protection_end:
        return 0
    remaining = (protection_end - datetime.utcnow()).total_seconds()
    return int(remaining) if remaining > 0 else 0


def is_user_protected(user: User) -> bool:
    """Check whether the user is still under protection."""
    return get_protection_seconds_left(user) > 0

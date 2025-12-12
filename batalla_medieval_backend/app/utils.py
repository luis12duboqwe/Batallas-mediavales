"""Utility functions for the application."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime.
    
    Replaces deprecated utc_now() with timezone-aware alternative.
    """
    return datetime.now(timezone.utc)


def get_utc_now() -> datetime:
    """Callable wrapper for SQLAlchemy default parameter.
    
    Use this for Column(DateTime, default=get_utc_now) to ensure
    timezone-aware datetime creation at database level.
    """
    return datetime.now(timezone.utc)

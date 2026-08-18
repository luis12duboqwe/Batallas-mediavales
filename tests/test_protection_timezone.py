from datetime import datetime, timezone

from app.services import protection


NOW = datetime(2026, 8, 18, 18, 0, tzinfo=timezone.utc)


def test_naive_sqlite_protection_end_is_treated_as_utc(user, monkeypatch):
    user.protection_ends_at = datetime(2026, 8, 18, 19, 0)
    monkeypatch.setattr(protection, "utc_now", lambda: NOW)

    assert protection.get_protection_end(user).tzinfo == timezone.utc
    assert protection.get_protection_seconds_left(user) == 3600
    assert protection.is_user_protected(user) is True


def test_aware_protection_end_uses_same_utc_calculation(user, monkeypatch):
    user.protection_ends_at = datetime(2026, 8, 18, 19, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(protection, "utc_now", lambda: NOW)

    assert protection.get_protection_seconds_left(user) == 3600


def test_expired_naive_protection_returns_zero(user, monkeypatch):
    user.protection_ends_at = datetime(2026, 8, 18, 17, 59, 59)
    monkeypatch.setattr(protection, "utc_now", lambda: NOW)

    assert protection.get_protection_seconds_left(user) == 0
    assert protection.is_user_protected(user) is False

import pytest
from pydantic import ValidationError

from app.config import Settings


STRONG_SECRET = "a-unique-production-secret-with-more-than-32-characters"
POSTGRES_URL = "postgresql+psycopg://user:password@database/game"


def protected_settings(**overrides):
    values = {
        "app_env": "production",
        "secret_key": STRONG_SECRET,
        "database_url": POSTGRES_URL,
        "cors_origins": ["https://game.example"],
        "frontend_url": "https://game.example",
        "smtp_host": "smtp.example",
        "from_email": "accounts@game.example",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    "secret_key",
    ["short", "supersecretkey", "replace-with-a-random-secret"],
)
def test_production_rejects_weak_secret(secret_key):
    with pytest.raises(ValidationError, match="requires a unique SECRET_KEY"):
        protected_settings(secret_key=secret_key)


@pytest.mark.parametrize(
    "cors_origins",
    [["*"], ["http://game.example"]],
)
def test_production_rejects_insecure_cors(cors_origins):
    with pytest.raises(ValidationError, match="explicit HTTPS CORS_ORIGINS"):
        protected_settings(cors_origins=cors_origins)


def test_production_rejects_sqlite():
    with pytest.raises(ValidationError, match="requires PostgreSQL"):
        protected_settings(database_url="sqlite:///production.db")


def test_production_rejects_http_frontend():
    with pytest.raises(ValidationError, match="requires an HTTPS FRONTEND_URL"):
        protected_settings(frontend_url="http://game.example")


@pytest.mark.parametrize(
    "overrides",
    [
        {"smtp_host": ""},
        {"from_email": ""},
        {"from_email": "invalid-address"},
    ],
)
def test_production_requires_account_email_delivery(overrides):
    with pytest.raises(ValidationError, match="requires SMTP_HOST"):
        protected_settings(**overrides)


def test_production_accepts_explicit_secure_configuration():
    settings = protected_settings(
        cors_origins=["https://game.example/", "https://admin.game.example"]
    )
    assert settings.cors_origins == [
        "https://game.example",
        "https://admin.game.example",
    ]
    assert settings.frontend_url == "https://game.example"
    assert settings.smtp_use_starttls is True


def test_cors_origins_accept_comma_separated_environment_value(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

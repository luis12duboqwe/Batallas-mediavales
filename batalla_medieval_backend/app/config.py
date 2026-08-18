import json
from typing import List, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROTECTED_ENVIRONMENTS = {"staging", "production"}
KNOWN_WEAK_SECRETS = {
    "change-me",
    "replace-with-a-random-secret",
    "supersecretkey",
    "development-only-secret-key-do-not-use",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
    )

    app_name: str = "Batalla Medieval"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    secret_key: str = "development-only-secret-key-do-not-use"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./batalla_medieval.db"
    protection_hours: int = 48
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_starttls: bool = True
    from_email: str = ""
    frontend_url: str = "http://localhost:5173"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, raw_value):
        if isinstance(raw_value, str):
            stripped = raw_value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [value.strip() for value in stripped.split(",") if value.strip()]
        return raw_value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: List[str]) -> List[str]:
        normalized: list[str] = []
        for origin in origins:
            value = origin.strip().rstrip("/")
            if not value:
                continue
            if value == "*":
                normalized.append(value)
                continue
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Invalid CORS origin: {origin}")
            if parsed.path or parsed.params or parsed.query or parsed.fragment:
                raise ValueError(f"CORS origins must not include a path: {origin}")
            normalized.append(value)

        if not normalized:
            raise ValueError("At least one CORS origin is required")
        return normalized

    @model_validator(mode="after")
    def reject_insecure_protected_environment(self):
        if self.app_env not in PROTECTED_ENVIRONMENTS:
            return self

        if len(self.secret_key) < 32 or self.secret_key in KNOWN_WEAK_SECRETS:
            raise ValueError(
                f"{self.app_env} requires a unique SECRET_KEY with at least 32 characters"
            )

        if self.database_url.startswith("sqlite"):
            raise ValueError(
                f"{self.app_env} requires PostgreSQL; SQLite is not allowed"
            )

        if "*" in self.cors_origins or any(
            not origin.startswith("https://") for origin in self.cors_origins
        ):
            raise ValueError(
                f"{self.app_env} requires explicit HTTPS CORS_ORIGINS and forbids '*'"
            )

        frontend_url = self.frontend_url.rstrip("/")
        if not frontend_url.startswith("https://"):
            raise ValueError(f"{self.app_env} requires an HTTPS FRONTEND_URL")
        self.frontend_url = frontend_url

        if not self.smtp_host.strip() or "@" not in self.from_email.strip():
            raise ValueError(
                f"{self.app_env} requires SMTP_HOST and a valid FROM_EMAIL for account verification"
            )

        return self


def get_settings() -> Settings:
    return Settings()

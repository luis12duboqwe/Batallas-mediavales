import json
from typing import List, Literal
from urllib.parse import urlparse

from pydantic import BaseSettings, Field, root_validator, validator


PROTECTED_ENVIRONMENTS = {"staging", "production"}
KNOWN_WEAK_SECRETS = {
    "change-me",
    "replace-with-a-random-secret",
    "supersecretkey",
    "development-only-secret-key-do-not-use",
}


class Settings(BaseSettings):
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

    @validator("cors_origins")
    def validate_cors_origins(cls, origins: List[str]) -> List[str]:
        normalized = []
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

    @root_validator
    def reject_insecure_protected_environment(cls, values):
        app_env = values.get("app_env")
        if app_env not in PROTECTED_ENVIRONMENTS:
            return values

        secret_key = values.get("secret_key", "")
        if len(secret_key) < 32 or secret_key in KNOWN_WEAK_SECRETS:
            raise ValueError(
                f"{app_env} requires a unique SECRET_KEY with at least 32 characters"
            )

        database_url = values.get("database_url", "")
        if database_url.startswith("sqlite"):
            raise ValueError(f"{app_env} requires PostgreSQL; SQLite is not allowed")

        cors_origins = values.get("cors_origins", [])
        if "*" in cors_origins or any(
            not origin.startswith("https://") for origin in cors_origins
        ):
            raise ValueError(
                f"{app_env} requires explicit HTTPS CORS_ORIGINS and forbids '*'"
            )

        frontend_url = str(values.get("frontend_url") or "").rstrip("/")
        if not frontend_url.startswith("https://"):
            raise ValueError(f"{app_env} requires an HTTPS FRONTEND_URL")
        values["frontend_url"] = frontend_url

        smtp_host = str(values.get("smtp_host") or "").strip()
        from_email = str(values.get("from_email") or "").strip()
        if not smtp_host or "@" not in from_email:
            raise ValueError(
                f"{app_env} requires SMTP_HOST and a valid FROM_EMAIL for account verification"
            )

        return values

    class Config:
        env_file = ".env"
        case_sensitive = False

        @classmethod
        def parse_env_var(cls, field_name: str, raw_value: str):
            if field_name == "cors_origins":
                stripped = raw_value.strip()
                if stripped.startswith("["):
                    return json.loads(stripped)
                return [value.strip() for value in stripped.split(",") if value.strip()]
            return cls.json_loads(raw_value)


def get_settings() -> Settings:
    return Settings()

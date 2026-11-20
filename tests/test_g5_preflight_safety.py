"""Regression tests for production/staging deployment preflight (stdlib-only logic)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PREFLIGHT_PATH = Path(__file__).resolve().parents[1] / "ops" / "preflight.py"
SPEC = importlib.util.spec_from_file_location("g5_preflight", PREFLIGHT_PATH)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def valid_env() -> dict[str, str]:
    sha = "a" * 40
    return {
        "APP_ENV": "staging",
        "SECRET_KEY": "rC4vKp93Bz2Q8ws6Hm7dJF5Lx0Ty31NqE",
        "DB_URL": "postgresql+psycopg://batalla:strong@database:5432/batalla_ci",
        "POSTGRES_USER": "batalla",
        "POSTGRES_PASSWORD": "strong",
        "POSTGRES_DB": "batalla_ci",
        "FRONTEND_URL": "https://staging.example.invalid",
        "PUBLIC_BASE_URL": "https://staging.example.invalid",
        "PUBLIC_HOST": "staging.example.invalid",
        "TLS_EMAIL": "admin@example.invalid",
        "HTTP_PORT": "80",
        "HTTPS_PORT": "443",
        "CORS_ORIGINS": "https://staging.example.invalid",
        "SMTP_HOST": "smtp.example.invalid",
        "FROM_EMAIL": "noreply@example.invalid",
        "SUPPORT_CONTACT": "help@example.invalid",
        "BACKEND_IMAGE": f"ghcr.io/team/game-backend:{sha}",
        "FRONTEND_IMAGE": f"ghcr.io/team/game-frontend:{sha}",
        "BACKUP_DIR": "/var/backups/game",
        "BACKUP_RETENTION_DAYS": "14",
        "LOAD_DURATION_SECONDS": "15",
        "LOAD_CONCURRENCY": "8",
        "MAX_P95_MS": "750",
        "MAX_ERROR_RATE": "0.005",
    }


def test_valid_protected_environment() -> None:
    assert preflight.validate(valid_env()) == []


def test_content_addressed_digest_is_accepted() -> None:
    env = valid_env()
    env["BACKEND_IMAGE"] = "ghcr.io/team/game-backend@sha256:" + "b" * 64
    assert preflight.validate(env) == []


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/team/game:latest",
        "ghcr.io/team/game:release1234",
        "ghcr.io/team/game:1234567890abcdef",
        "ghcr.io/team/game@sha256:",
        "ghcr.io/team/game@sha256:broken",
        "ghcr.io/team/game@sha256:" + "f" * 63,
        "ghcr.io/team/game@sha256:" + "f" * 65,
        "ghcr.io/team/game:latest@sha256:" + "b" * 64,
        "ghcr.io/team/game:" + "z" * 40,
    ],
)
def test_mutable_or_malformed_image_rejected(image: str) -> None:
    env = valid_env()
    env["BACKEND_IMAGE"] = image
    assert any("BACKEND_IMAGE" in error for error in preflight.validate(env))


@pytest.mark.parametrize(
    "secret",
    [
        "replace-with-at-least-32-random-characters",
        "REPLACE-WITH-AT-LEAST-32-RANDOM-CHARACTERS",
        "change-me" * 7,
        "example-placeholder-not-a-valid-secret-12345",
        "too-short",
    ],
)
def test_placeholder_secrets_rejected(secret: str) -> None:
    env = valid_env()
    env["SECRET_KEY"] = secret
    assert any("SECRET_KEY" in error for error in preflight.validate(env))


@pytest.mark.parametrize(
    "database",
    [
        "game'; DROP DATABASE postgres;--",
        "with-hyphen",
        "with space",
        "../game",
        "0initial_digit",
        "a" * 64,
    ],
)
def test_unsafe_database_identifiers_rejected(database: str) -> None:
    env = valid_env()
    env["POSTGRES_DB"] = database
    assert any("POSTGRES_DB" in error for error in preflight.validate(env))


@pytest.mark.parametrize(
    "origin",
    [
        "https://:443",
        "https://staging.example.invalid:broken",
        "https://staging.example.invalid:65536",
        "https://staging.example.invalid:0",
        "https://staging.example.invalid/login",
        "https://staging.example.invalid/?token=x",
        "https://user:password@staging.example.invalid",
        "http://staging.example.invalid",
    ],
)
def test_invalid_frontend_origins_rejected(origin: str) -> None:
    env = valid_env()
    env["FRONTEND_URL"] = origin
    assert any("FRONTEND_URL" in error for error in preflight.validate(env))


def test_explicit_https_origin_with_valid_port_is_accepted() -> None:
    env = valid_env()
    env["FRONTEND_URL"] = "https://staging.example.invalid:8443/"
    assert preflight.validate(env) == []


def test_cors_origin_path_is_rejected() -> None:
    env = valid_env()
    env["CORS_ORIGINS"] = "https://staging.example.invalid/account"
    assert any("CORS_ORIGINS" in error for error in preflight.validate(env))


def test_read_env_does_not_import_application(tmp_path: Path) -> None:
    dotenv = tmp_path / "example.env"
    dotenv.write_text("export APP_ENV=staging\nSECRET_KEY='test secret'\n", encoding="utf-8")
    assert preflight.read_env(dotenv) == {"APP_ENV": "staging", "SECRET_KEY": "test secret"}

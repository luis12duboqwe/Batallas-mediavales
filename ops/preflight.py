#!/usr/bin/env python3
"""Validate a staging/production deployment environment before mutation.

The script deliberately reads a dotenv-style file without importing the app so it
can run on a clean deployment host before images or Python dependencies exist.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

PROTECTED_ENVIRONMENTS = {"staging", "production"}
WEAK_SECRETS = {
    "change-me",
    "replace-with-a-random-secret",
    "supersecretkey",
    "development-only-secret-key-do-not-use",
}
IMMUTABLE_IMAGE_RE = re.compile(r"^.+:[A-Za-z0-9][A-Za-z0-9_.-]{6,}$")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'\"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def require(values: dict[str, str], key: str, errors: list[str]) -> str:
    value = values.get(key, "").strip()
    if not value:
        errors.append(f"{key} is required")
    return value


def validate_https_url(name: str, value: str, errors: list[str]) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append(f"{name} must be an absolute https:// URL")


def validate_email(name: str, value: str, errors: list[str]) -> None:
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        errors.append(f"{name} must be a valid email address")


def validate_image(name: str, value: str, errors: list[str]) -> None:
    if not value:
        return
    lowered = value.lower()
    if lowered.endswith(":latest") or ":latest@" in lowered:
        errors.append(f"{name} must use an immutable release tag, never :latest")
        return
    if "@sha256:" in value:
        return
    if not IMMUTABLE_IMAGE_RE.match(value):
        errors.append(f"{name} must include an explicit immutable tag or digest")


def validate_positive_number(
    values: dict[str, str], key: str, default: str, errors: list[str]
) -> float | None:
    raw = values.get(key, default).strip()
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{key} must be numeric")
        return None
    if value <= 0:
        errors.append(f"{key} must be positive")
        return None
    return value


def validate(values: dict[str, str]) -> list[str]:
    errors: list[str] = []

    app_env = require(values, "APP_ENV", errors)
    if app_env and app_env not in PROTECTED_ENVIRONMENTS:
        errors.append("APP_ENV must be staging or production for deployment")

    secret = require(values, "SECRET_KEY", errors)
    if secret and (len(secret) < 32 or secret in WEAK_SECRETS):
        errors.append("SECRET_KEY must be unique and at least 32 characters")

    db_url = require(values, "DB_URL", errors)
    if db_url and not db_url.startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("DB_URL must use PostgreSQL")

    require(values, "POSTGRES_USER", errors)
    require(values, "POSTGRES_PASSWORD", errors)
    require(values, "POSTGRES_DB", errors)

    frontend_url = require(values, "FRONTEND_URL", errors)
    if frontend_url:
        validate_https_url("FRONTEND_URL", frontend_url, errors)

    public_base_url = require(values, "PUBLIC_BASE_URL", errors)
    if public_base_url:
        validate_https_url("PUBLIC_BASE_URL", public_base_url, errors)

    cors_raw = require(values, "CORS_ORIGINS", errors)
    if cors_raw:
        origins = [part.strip() for part in cors_raw.split(",") if part.strip()]
        if not origins or "*" in origins:
            errors.append("CORS_ORIGINS must be explicit and cannot contain '*'")
        for origin in origins:
            validate_https_url("CORS_ORIGINS entry", origin, errors)

    require(values, "SMTP_HOST", errors)
    from_email = require(values, "FROM_EMAIL", errors)
    if from_email:
        validate_email("FROM_EMAIL", from_email, errors)

    support_contact = require(values, "SUPPORT_CONTACT", errors)
    if support_contact:
        validate_email("SUPPORT_CONTACT", support_contact, errors)

    backend_image = require(values, "BACKEND_IMAGE", errors)
    frontend_image = require(values, "FRONTEND_IMAGE", errors)
    validate_image("BACKEND_IMAGE", backend_image, errors)
    validate_image("FRONTEND_IMAGE", frontend_image, errors)

    backup_dir = require(values, "BACKUP_DIR", errors)
    if backup_dir and not backup_dir.startswith("/"):
        errors.append("BACKUP_DIR must be an absolute host path")

    retention = require(values, "BACKUP_RETENTION_DAYS", errors)
    if retention:
        try:
            if int(retention) < 1:
                raise ValueError
        except ValueError:
            errors.append("BACKUP_RETENTION_DAYS must be a positive integer")

    load_duration = validate_positive_number(
        values, "LOAD_DURATION_SECONDS", "15", errors
    )
    load_concurrency = validate_positive_number(
        values, "LOAD_CONCURRENCY", "8", errors
    )
    max_p95 = validate_positive_number(values, "MAX_P95_MS", "750", errors)
    max_error_raw = values.get("MAX_ERROR_RATE", "0.005").strip()
    try:
        max_error_rate = float(max_error_raw)
        if not 0 <= max_error_rate <= 1:
            raise ValueError
    except ValueError:
        errors.append("MAX_ERROR_RATE must be between 0 and 1")

    if load_duration is not None and load_duration > 3600:
        errors.append("LOAD_DURATION_SECONDS cannot exceed 3600")
    if load_concurrency is not None and (
        load_concurrency < 1 or not load_concurrency.is_integer()
    ):
        errors.append("LOAD_CONCURRENCY must be a positive integer")
    if max_p95 is not None and max_p95 > 10000:
        errors.append("MAX_P95_MS cannot exceed 10000")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("env_file", type=Path)
    args = parser.parse_args()

    if not args.env_file.is_file():
        print(f"preflight failed: env file not found: {args.env_file}", file=sys.stderr)
        return 2

    try:
        values = read_env(args.env_file)
    except (OSError, ValueError) as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 2

    errors = validate(values)
    if errors:
        print("deployment preflight failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"deployment preflight passed for {values['APP_ENV']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

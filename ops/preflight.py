#!/usr/bin/env python3
"""Validate a staging/production deployment environment before mutation.

The script deliberately reads a dotenv-style file without importing the app so it
can run on a clean deployment host before images or Python dependencies exist.
"""

from __future__ import annotations

import argparse
import math
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
# Protected deployments only accept tags tied to a full Git SHA, or a
# content-addressed SHA-256 digest. Arbitrary tags can be overwritten.
IMAGE_REPO_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*(?::[0-9]{1,5})?(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+$"
)
IMAGE_SHA_TAG_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_SHA_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# This value is interpolated into a psql statement during restore.
POSTGRES_DB_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
HOST_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")


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
    try:
        parsed = urlparse(value)
        port = parsed.port  # Access raises ValueError for malformed/out-of-range ports.
        hostname = parsed.hostname
    except ValueError:
        errors.append(f"{name} must be an absolute https:// URL with a valid port")
        return
    if parsed.scheme != "https" or not parsed.netloc or not hostname or port == 0:
        errors.append(f"{name} must be an absolute https:// URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        errors.append(f"{name} must not contain credentials, query parameters or fragments")
    if parsed.path not in ("", "/") or parsed.params:
        errors.append(f"{name} must be an origin URL without a path")


def validate_email(name: str, value: str, errors: list[str]) -> None:
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        errors.append(f"{name} must be a valid email address")


def validate_image(name: str, value: str, errors: list[str]) -> None:
    if not value:
        return
    if value.lower().endswith(":latest") or ":latest@" in value.lower():
        errors.append(f"{name} must use an immutable release tag, never :latest")
        return

    if "@" in value:
        repository, separator, digest = value.partition("@")
        valid = separator and IMAGE_SHA_DIGEST_RE.fullmatch(digest)
    else:
        repository, separator, tag = value.rpartition(":")
        valid = separator and IMAGE_SHA_TAG_RE.fullmatch(tag)

    if not valid or not IMAGE_REPO_RE.fullmatch(repository):
        errors.append(f"{name} must use a full 40-character Git SHA tag or a 64-hex SHA-256 digest")


def validate_positive_number(
    values: dict[str, str], key: str, default: str, errors: list[str]
) -> float | None:
    raw = values.get(key, default).strip()
    try:
        value = float(raw)
    except ValueError:
        errors.append(f"{key} must be numeric")
        return None
    if not math.isfinite(value) or value <= 0:
        errors.append(f"{key} must be a finite positive number")
        return None
    return value


def validate_port(values: dict[str, str], key: str, default: str, errors: list[str]) -> int | None:
    raw = values.get(key, default).strip()
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{key} must be an integer TCP/UDP port")
        return None
    if not 1 <= value <= 65535:
        errors.append(f"{key} must be between 1 and 65535")
        return None
    return value


def validate(values: dict[str, str]) -> list[str]:
    errors: list[str] = []

    app_env = require(values, "APP_ENV", errors)
    if app_env and app_env not in PROTECTED_ENVIRONMENTS:
        errors.append("APP_ENV must be staging or production for deployment")

    secret = require(values, "SECRET_KEY", errors)
    if secret and (
        len(secret) < 32
        or secret.lower() in WEAK_SECRETS
        or secret.lower().startswith(("replace-", "change-me", "example-"))
    ):
        errors.append("SECRET_KEY must not be a placeholder and must have at least 32 characters")

    db_url = require(values, "DB_URL", errors)
    if db_url and not db_url.startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("DB_URL must use PostgreSQL")

    require(values, "POSTGRES_USER", errors)
    require(values, "POSTGRES_PASSWORD", errors)
    db_name = require(values, "POSTGRES_DB", errors)
    if db_name and not POSTGRES_DB_RE.fullmatch(db_name):
        errors.append("POSTGRES_DB must be a simple PostgreSQL identifier (letters, digits, underscore)")

    frontend_url = require(values, "FRONTEND_URL", errors)
    if frontend_url:
        validate_https_url("FRONTEND_URL", frontend_url, errors)

    public_base_url = require(values, "PUBLIC_BASE_URL", errors)
    if public_base_url:
        validate_https_url("PUBLIC_BASE_URL", public_base_url, errors)

    public_host = require(values, "PUBLIC_HOST", errors)
    if public_host:
        if "://" in public_host or "/" in public_host or not HOST_RE.match(public_host):
            errors.append("PUBLIC_HOST must be a DNS hostname without scheme, path or port")
        if public_base_url:
            parsed_host = (urlparse(public_base_url).hostname or "").lower()
            if parsed_host and public_host.lower() != parsed_host:
                errors.append("PUBLIC_HOST must match the hostname in PUBLIC_BASE_URL")

    tls_email = require(values, "TLS_EMAIL", errors)
    if tls_email:
        validate_email("TLS_EMAIL", tls_email, errors)

    http_port = validate_port(values, "HTTP_PORT", "80", errors)
    https_port = validate_port(values, "HTTPS_PORT", "443", errors)
    if http_port is not None and https_port is not None and http_port == https_port:
        errors.append("HTTP_PORT and HTTPS_PORT must be different")

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

    load_duration = validate_positive_number(values, "LOAD_DURATION_SECONDS", "15", errors)
    load_concurrency = validate_positive_number(values, "LOAD_CONCURRENCY", "8", errors)
    load_target_rps = validate_positive_number(values, "LOAD_TARGET_RPS", "6", errors)
    max_p95 = validate_positive_number(values, "MAX_P95_MS", "750", errors)
    max_error_raw = values.get("MAX_ERROR_RATE", "0.005").strip()
    try:
        max_error_rate = float(max_error_raw)
        if not math.isfinite(max_error_rate) or not 0 <= max_error_rate <= 1:
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
    if load_target_rps is not None and load_target_rps > 10:
        errors.append("LOAD_TARGET_RPS must not exceed the protected proxy limit of 10 requests/s")

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
